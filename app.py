#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- mode: python -*-
""" """
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.request import BoltRequest


@dataclass
class Auction:
    """Models a sealed-bid auction. Each participant may submit one sealed bid.
    The auction is over when every participant has bid."""

    active: bool = False
    participants: set[str] = field(default_factory=set)
    bids: dict[str, str] = field(default_factory=dict)

    def begin(self, participants):
        self.participants = set(participants)
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
auction = Auction()


def get_channel_users(client, channel):
    me = client.auth_test().data["user_id"]
    users = client.conversations_members(channel=channel).data["members"]
    return set(users).difference([me])


def start_auction(say, command, client):
    user = command["user_id"]
    channel = command["channel_id"]
    participants = get_channel_users(client, channel)
    participant_list = ",".join(f"<@{user}>" for user in participants)

    auction.begin(participants)

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<@{user}> has initiated an auction. Awaiting bids from {participant_list}. "
                "Bids will be revealed once everyone has placed theirs. Until then, bids can be changed. "
                "Commands: `/auction cancel` will terminate the auction without revealing bids. "
                "`/auction poke` will notify all participants who have not yet bid.",
            },
        },
        {
            "dispatch_action": True,
            "type": "input",
            "element": {
                "type": "plain_text_input",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Enter a number (or 'pass')",
                },
                "action_id": "bid_placed-action",
            },
            "label": {"type": "plain_text", "text": "Your bid:", "emoji": True},
        },
    ]
    say(blocks=blocks, text=f"<@{user}> is initiating an auction!", channel=channel)


def stop_auction(say, respond, command):
    user = command["user_id"]
    channel = command["channel_id"]
    if auction.active:
        auction.end()
        say(
            text=f"<@{user}> has canceled the auction. All bids have been discarded.",
            channel=channel,
        )
    else:
        respond("No auction is in progress.")


def poke_users(say, respond, command):
    channel = command["channel_id"]
    if auction.active:
        to_be_poked = ",".join(f"<@{user}>" for user in auction.has_not_bid)
        say(text=f"Waiting on {to_be_poked} for bids", channel=channel)
    else:
        respond("No one to poke: no auction is in progress.")


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


@app.command("/auction")
def handle_command(ack, say, respond, command, client):
    ack()
    if command["text"].startswith("poke"):
        poke_users(say, respond, command)
    elif command["text"].startswith("cancel"):
        stop_auction(say, respond, command)
    elif auction.active:
        respond(
            "An auction is already running. Let it finish, or use `/auction cancel` to end it"
        )
    else:
        start_auction(say, command, client)


@app.action("bid_placed-action")
def handle_bid(ack, say, body, client):
    ack()
    bid = body["actions"][0]["value"]
    user = body["user"]["id"]
    trigger_id = body["trigger_id"]
    if not auction.active:
        client.views_open(
            trigger_id=trigger_id,
            view=make_modal_text(
                "Error", "No auction is active. Start one with `/auction init`"
            ),
        )
    else:
        auction.bid(user, bid)
        if auction.done:
            results = "\n\n".join(
                f" - <@{user}>: {bid}" for user, bid in auction.bids.items()
            )
            text = f"The auction has concluded! The bids were:\n\n {results}"
            say(text=text)
            auction.end()
        else:
            client.views_open(
                trigger_id=trigger_id,
                view=make_modal_text(
                    "Bid received",
                    f"Your bid of {bid} has been recorded. It can be changed until all users have bid.",
                ),
            )


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
