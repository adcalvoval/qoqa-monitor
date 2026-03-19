import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(sender: str, app_password: str, recipient: str, matches: list[dict]) -> bool:
    """
    Send a summary email listing all matching offers.
    Returns True on success, False on failure.
    """
    if matches:
        subject = f"[QoQa Monitor] {len(matches)} matching offer(s) found!"
    else:
        subject = "[QoQa Monitor] No matching offers today"

    # Build plain-text body
    if matches:
        text_lines = [
            f"QoQa Monitor found {len(matches)} offer(s) matching your keywords.\n",
        ]
        for i, offer in enumerate(matches, 1):
            keywords_str = ", ".join(offer["matched_keywords"])
            text_lines.append(f"{'='*60}")
            text_lines.append(f"Offer #{i}: {offer['title']}")
            text_lines.append(f"Keywords matched: {keywords_str}")
            text_lines.append(f"URL: {offer['url']}")
            text_lines.append(f"Details: {offer['description'][:400]}...")
            text_lines.append("")
    else:
        text_lines = ["QoQa Monitor ran its daily check but found no offers matching your keywords.\n"]

    text_body = "\n".join(text_lines)

    # Build HTML body
    if matches:
        html_parts = [
            "<html><body>",
            f"<h2>QoQa Monitor — {len(matches)} matching offer(s) found</h2>",
        ]
        for i, offer in enumerate(matches, 1):
            keywords_str = ", ".join(f"<strong>{kw}</strong>" for kw in offer["matched_keywords"])
            html_parts.append("<hr>")
            html_parts.append(f"<h3>#{i} — {offer['title']}</h3>")
            html_parts.append(f"<p>Keywords matched: {keywords_str}</p>")
            html_parts.append(f'<p><a href="{offer["url"]}">View on QoQa</a></p>')
            html_parts.append(f"<p>{offer['description'][:500]}...</p>")
        html_parts.append("</body></html>")
    else:
        html_parts = [
            "<html><body>",
            "<h2>QoQa Monitor — No matching offers today</h2>",
            "<p>The daily check ran but found no offers matching your keywords.</p>",
            "</body></html>",
        ]
    html_body = "\n".join(html_parts)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, recipient, msg.as_string())
        logger.info(f"Email sent to {recipient}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail authentication failed. Check your app password.")
        return False
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
