
# Vickreybot

A very simple slack app for running Vickrey auctions or any other kind of activity where everyone in the channel needs to make some commitment in secret. 

## Installation

Create a new slack app: https://api.slack.com/apps.

Create a `.env` file and add the following secrets to it:

```
APP_ID=
CLIENT_ID=
CLIENT_SECRET=
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
```

Create a virtual environment and install dependencies:

``` shell
python3 -m venv venv
venv/bin/python -m install --upgrade setuptools pip wheel
venv/bin/python -m install -r requirements.txt
```

Run the app:

``` shell
venv/bin/python app.py
```
