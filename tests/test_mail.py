from email.message import EmailMessage
from unittest import TestCase

from maildigest.mail import parse_message, quote_mailbox


class MailParsingTests(TestCase):
    def test_mailbox_names_are_safely_quoted(self) -> None:
        self.assertEqual(quote_mailbox("Folders/TLDR Dev"), '"Folders/TLDR Dev"')
        self.assertEqual(quote_mailbox('A "quoted" folder'), '"A \\"quoted\\" folder"')

    def test_prefers_plain_text_and_ignores_attachments(self) -> None:
        message = EmailMessage()
        message["From"] = "Alice <alice@example.com>"
        message["Subject"] = "Caf\u00e9 update"
        message["Date"] = "Wed, 12 Aug 2026 09:30:00 +0200"
        message.set_content("Please review the report.\n")
        message.add_alternative("<p>HTML fallback</p>", subtype="html")
        message.add_attachment(b"secret attachment", maintype="application", subtype="octet-stream", filename="x.bin")

        parsed = parse_message("42", message.as_bytes(), 1000)

        self.assertEqual(parsed["uid"], "42")
        self.assertEqual(parsed["subject"], "Caf\u00e9 update")
        self.assertEqual(parsed["body"], "Please review the report.")
        self.assertNotIn("secret attachment", parsed["body"])

    def test_html_only_message_becomes_text(self) -> None:
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message.set_content(
            '<p>Hello &amp; welcome</p><a href="https://example.com/story">Important AI story (3 minute read)</a>'
            '<a href="https://example.com/job">Apply here</a>'
            '<a href="mailto:person@example.com">Email us</a><script>bad()</script>',
            subtype="html",
        )
        parsed = parse_message("1", message.as_bytes(), 1000)
        self.assertIn("Hello & welcome", parsed["body"])
        self.assertNotIn("bad()", parsed["body"])
        self.assertEqual(
            parsed["links"],
            [{"label": "Important AI story (3 minute read)", "url": "https://example.com/story"}],
        )
