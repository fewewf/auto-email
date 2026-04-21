import os
import json
import time
import smtplib
import requests
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import re


# =========================
# 1. 配置加载
# =========================
def load_email_config():
    raw = os.getenv("EMAIL_CONFIG")
    if not raw:
        raise ValueError("EMAIL_CONFIG 未配置")

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"EMAIL_CONFIG JSON 错误: {e}")

    required = [
        "smtp_server", "smtp_port", "smtp_user",
        "smtp_pass", "from_email", "to_emails", "subject"
    ]

    for k in required:
        if k not in config:
            raise ValueError(f"缺少字段: {k}")

    if isinstance(config["to_emails"], str):
        config["to_emails"] = [
            x.strip() for x in config["to_emails"].split(",")
        ]

    return config


def load_email_body():
    body = os.getenv("EMAIL_BODY")
    if not body:
        raise ValueError("EMAIL_BODY 未配置")
    return body


def load_telegram():
    return os.getenv("TG_ID"), os.getenv("TG_TOKEN")


# =========================
# 2. 邮件 HTML 处理
# =========================
def format_html(body: str) -> str:
    return f"""
    <div style="
        white-space: pre-wrap;
        font-family: Arial, sans-serif;
        line-height: 1.5;
        font-size: 14px;
    ">
        {body}
    </div>
    """


# =========================
# 3. SMTP 发送（带重试）
# =========================
def send_email_with_retry(server, port, user, password,
                          from_email, to_email,
                          subject, body, retry=3):

    for attempt in range(1, retry + 1):
        try:
            msg = MIMEMultipart()
            msg["From"] = from_email
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(format_html(body), "html"))

            if port == 465:
                smtp = smtplib.SMTP_SSL(server, port)
            else:
                smtp = smtplib.SMTP(server, port)
                smtp.starttls()

            smtp.login(user, password)
            smtp.sendmail(from_email, to_email, msg.as_string())
            smtp.quit()

            print(f"✔ 成功")
            return True, None

        except Exception as e:
            err = str(e)
            print(f"⚠ 第 {attempt} 次失败 {to_email}: {err}")

            time.sleep(2 * attempt)

            if attempt == retry:
                return False, err


# =========================
# 4. Telegram 通知
# =========================
def send_telegram(tg_id, tg_token, success, failed):
    if not tg_id or not tg_token:
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    text = [
        "📧 邮件群发报告",
        f"⏰ {now}",
        f"✔ 成功: {len(success)}",
        f"✖ 失败: {len(failed)}",
        ""
    ]

    for s in success:
        text.append(f"✔ {s}")

    for f, r in failed.items():
        text.append(f"✖ {f} -> {r}")

    msg = "\n".join(text)

    # MarkdownV2 escape
    escaped = re.sub(r'([\\_*[\]()~`>#+\-=|{}.!])', r'\\\1', msg)
    final = f"||{escaped}||"

    url = f"https://api.telegram.org/bot{tg_token}/sendMessage"

    try:
        requests.post(url, json={
            "chat_id": tg_id,
            "text": final,
            "parse_mode": "MarkdownV2"
        })
    except Exception as e:
        print("Telegram 失败:", e)


# =========================
# 5. 主流程
# =========================
if __name__ == "__main__":
    try:
        config = load_email_config()
        body = load_email_body()
        tg_id, tg_token = load_telegram()

        success_list = []
        failed_map = {}

        for email in config["to_emails"]:
            ok, err = send_email_with_retry(
                config["smtp_server"],
                int(config["smtp_port"]),
                config["smtp_user"],
                config["smtp_pass"],
                config["from_email"],
                email,
                config["subject"],
                body
            )

            if ok:
                success_list.append(email)
            else:
                failed_map[email] = err

        send_telegram(tg_id, tg_token, success_list, failed_map)

    except Exception as e:
        print("❌ 系统崩溃:", str(e))
        traceback.print_exc()
