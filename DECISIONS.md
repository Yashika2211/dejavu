# Decisions

One line each: decision, then why.

- Spec reconstructed from two pastes; the few lost words at the end of 7.2 are read as "feedback, postmortems, Slack threads". The surrounding rules make the intent unambiguous.
- Commits authored as `Yashika` with the GitHub no-reply address and no AI trailers. The owner asked for this, and it overrides spec rule 5's "commit at green checkpoints" cadence: every file or edit gets its own commit and push.
- Python 3.12 is installed through uv (the system Python is 3.9). The spec pins 3.12, and uv manages it per project.
