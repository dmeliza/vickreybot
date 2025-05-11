#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- mode: python -*-
""" """

import os
import re
from dataclasses import dataclass, field
from collections import defaultdict

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler


@dataclass
class Auction:
    """Models a sealed-bid auction. Each participant may submit one sealed bid.
    The auction is over when every participant has bid."""

    active: bool = False
    participants: set[str] = field(default_factory=set)
    bids: dict[str, str] = field(default_factory=dict)

    def set_participants(self, participants):
        self.participants = set(participants)

    def begin(self):
        self.bids = dict()
        self.active = True

    def end(self):
        self.active = False

    def bid(self, participant: str, value):
        if not self.active:
            raise ValueError("The auction is not active")
        if participant not in self.participants:
            raise ValueError(f"{participant} is not participating in this auction")
        self.bids[participant] = value

    @property
    def has_not_bid(self) -> set[str]:
        return self.participants.difference(self.bids.keys())

    @property
    def done(self) -> bool:
        return len(self.has_not_bid) == 0


load_dotenv()
app = App(token=os.environ["SLACK_BOT_TOKEN"])
auctions = defaultdict(Auction)


def get_channel_users(client, channel):
    me = client.auth_test().data["user_id"]
    users = client.conversations_members(channel=channel).data["members"]
    return set(users).difference([me])


def config_active_users(respond, command, client):
    channel = command["channel_id"]
    auction = auctions[channel]
    command = command["text"].strip()
    if auction.active:
        respond(
            "An auction is currently running. Let it finish, or use `/auction cancel` to end it before reconfiguring participants."
        )
        return

    players = set(re.findall(r"@[\w.-]+", command))
    if len(players) == 0:
        respond("`/auction players <@user1> <@user2> ... ` ", response_type="ephemeral")
        return
    valid_users = []
    try:
        channel_users = client.conversations_members(channel=channel).data["members"]
        for handle in players:
            user_id = handle[1:]  # remove `@`
            if user_id in channel_users:
                valid_users.append(user_id)
    except Exception as err:
        respond(f"Error validating channel members: {err}", response_type="ephemeral")
        return
    if valid_users:
        users_list = ", ".join([f"<@{user}>" for user in valid_users])
        respond(
            f"Auction participants updated: {users_list}\n", response_type="in_channel"
        )
        auction.set_participants(valid_users)
    else:
        respond(
            "Unable to update participants: no valid handles provided\n",
            response_type="ephemeral",
        )


def start_auction(respond, command, client):
    user = command["user_id"]
    channel = command["channel_id"]
    auction = auctions[channel]

    if auction.active:
        respond(
            "An auction is already running. Let it finish, or use `/auction cancel` to end it"
        )
        return
    if not auction.participants:
        respond(
            "The participant list is empty. Set it with `/auction players <list of handles>`",
            response_type="ephemeral",
        )
        return

    auction.begin()
    participant_list = ", ".join(f"<@{user}>" for user in auction.participants)
    respond(
        f"<@{user}> has initiated an auction. Use `/bid` to place your sealed bid. Awaiting bids from {participant_list}.",
        response_type="in_channel",
    )


def stop_auction(respond, command):
    user = command["user_id"]
    channel = command["channel_id"]
    if auctions[channel].active:
        auctions[channel].end()
        respond(
            f"<@{user}> has canceled the auction. All bids have been discarded.",
            response_type="in_channel",
        )
    else:
        respond("No auction is in progress in this channel.")


def poke_users(respond, command):
    channel = command["channel_id"]
    if auctions[channel].active:
        to_be_poked = ",".join(f"<@{user}>" for user in auctions[channel].has_not_bid)
        respond(f"Waiting on {to_be_poked} for bids", response_type="in_channel")
    else:
        respond("No one to poke: no auction is in progress in this channel.")


def make_modal_text(title, message):
    return {
        "type": "modal",
        "callback_id": "bid_ack_view",
        "title": {"type": "plain_text", "text": title},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message,
                },
            }
        ],
    }


def get_usage():
    return (
        "Hello! I understand these commands:\n\n"
        " - `/auction players` - set the list of active players\n\n"
        " - `/auction start` - start an auction\n\n"
        " - `/auction cancel` - cancel an auction\n\n"
        " - `/auction poke` - poke users who have not bid in an auction\n\n"
    )


@app.command("/auction")
def handle_command(ack, respond, command, client):
    ack()
    if command["text"].startswith("poke"):
        poke_users(respond, command)
    elif command["text"].startswith("cancel"):
        stop_auction(respond, command)
    elif command["text"].startswith("start"):
        start_auction(respond, command, client)
    elif command["text"].startswith("players"):
        config_active_users(respond, command, client)
    else:
        respond(get_usage())


@app.command("/bid")
def handle_bid(ack, respond, command, client):
    ack()
    user = command["user_id"]
    channel = command["channel_id"]
    bid = command["text"]
    auction = auctions[channel]
    if len(bid) == 0:
        respond("`/bid` an amount (or a message to pass)", response_type="ephemeral")
    elif not auction.active:
        respond(
            "No auction is active. Start one with `/auction start`",
            response_type="ephemeral",
        )
    else:
        auction.bid(user, bid)
        if not auction.done:
            respond(
                f"Your bid of *{bid}* has been recorded. It can be changed until all users have bid.",
                response_type="ephemeral",
            )
        else:
            results = "\n\n".join(
                f" - <@{user}>: {bid}" for user, bid in auction.bids.items()
            )
            text = f"The auction has concluded! The bids were:\n\n {results}"
            respond(text, response_type="in_channel")
            auction.end()


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
