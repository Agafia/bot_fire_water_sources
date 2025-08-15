# Manual Testing Plan

## Introduction

This document provides a plan for manually testing the Fire Water Sources Bot. The purpose of this testing is to identify any bugs or usability issues that were not caught by the automated tests.

## Prerequisites

Before you begin testing, you will need the following:

*   A Telegram account.
*   The username of the bot to be tested.

## Test Cases

| Test Case ID | Test Case Description | Steps to Reproduce | Expected Result | Actual Result | Status (Pass/Fail) |
| --- | --- | --- | --- | --- | --- |
| TC-001 | Start the bot and see the welcome message. | 1. Open a chat with the bot.<br>2. Send the `/start` command. | The bot should reply with a welcome message and ask for the identifier. | |
| TC-002 | Enter a valid identifier. | 1. Start the bot.<br>2. When prompted, enter a valid numeric identifier. | The bot should acknowledge the identifier and ask for the location. | |
| TC-003 | Enter an invalid identifier. | 1. Start the bot.<br>2. When prompted, enter a non-numeric identifier. | The bot should reply with an error message and ask for a valid identifier again. | |
| TC-004 | Complete the survey with valid data. | 1. Go through the entire survey, providing valid data for each step. | The bot should save the data and send a confirmation message. | |
| TC-005 | Use the `/stop` command during the survey. | 1. Start the survey.<br>2. At any point, send the `/stop` command. | The bot should stop the survey and clear the state. | |
| TC-006 | Use the `/help` command. | 1. Send the `/help` command. | The bot should reply with a help message containing useful links. | |
