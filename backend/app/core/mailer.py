"""Outgoing email. A real SMTP provider is chosen in slice 0.8 (docs/infra-signup.md).

Development and tests use `MemoryMailer`: messages are kept in memory (tests read them) and,
in dev, printed to the console so you can click invitation and reset links. Links contain
one-time tokens, so they are never written to the structured application log.
"""

import sys
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Email:
    to: str
    subject_key: str  # translation key; rendering in the user's language comes with templates
    link: str


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


@dataclass
class MemoryMailer:
    echo: bool = False
    sent: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> None:
        self.sent.append(email)
        if self.echo:
            print(
                f"[dev mail] to={email.to} subject={email.subject_key} link={email.link}",
                file=sys.stderr,
            )
