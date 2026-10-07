# Security policy

Sirina records conversations, so security and privacy problems matter a lot to us.

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Instead, report them privately
through GitHub: go to the repository's **Security** tab and choose **Report a vulnerability**.

Include the affected version or commit, steps to reproduce and the impact you see. You'll get a
reply within a week.

## Scope

In scope:

- the backend API, which listens on `127.0.0.1` only;
- handling of recordings, transcripts, voice fingerprints and API keys;
- the native helpers;
- the packaged app.

Not in scope: models downloaded from Hugging Face, and third-party AI providers you choose to
connect.

## Supported versions

Only the latest commit on `main` receives fixes.
