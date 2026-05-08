import os
import psycopg2
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime

# =========================
# ENV
# =========================
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
cursor = conn.cursor()

# =========================
# SELLER SCHEMA
# =========================
SELLER_SCHEMA = [
    ("city", str, False),
    ("locality", str, False),
    ("street", str, True),
    ("landmark", str, True),
    ("latitude", float, True),
    ("longitude", float, True),
    ("propertyName", str, False),
    ("propertyType", str, False),
    ("parking", str, True),
]

# =========================
def select_role():
    print("1. Buyer\n2. Seller")
    return "buyer" if input("Role: ") == "1" else "seller"

# =========================
def register_user():
    mobile = input("Mobile: ")
    name = input("Name: ")
    city = input("City: ").strip().title()

    cursor.execute('SELECT id FROM "User" WHERE mobile=%s', (mobile,))
    user = cursor.fetchone()

    if user:
        return user[0], city

    cursor.execute("""
        INSERT INTO "User"(mobile,name,city,"createdAt")
        VALUES (%s,%s,%s,NOW())
        RETURNING id
    """, (mobile, name, city))

    conn.commit()
    return cursor.fetchone()[0], city

# =========================
def search(city):
    cursor.execute("""
        SELECT id, city, locality, "propertyName", "propertyType"
        FROM "Property"
        WHERE LOWER(city) = LOWER(%s)
        LIMIT 10
    """, (city,))
    return cursor.fetchall()

# =========================
def validate_property(pid):
    cursor.execute('SELECT id FROM "Property" WHERE id=%s', (pid,))
    return cursor.fetchone() is not None

# =========================
def save_view(uid, pid):
    cursor.execute("""
        INSERT INTO "PropertyView"
        ("userId","propertyId","createdAt")
        VALUES (%s,%s,NOW())
        ON CONFLICT ("userId","propertyId") DO NOTHING
    """, (uid, pid))
    conn.commit()

# =========================
def like(uid, pid):
    if not validate_property(pid):
        print("❌ Invalid Property ID")
        return

    cursor.execute("""
        INSERT INTO "Like"
        ("userId","propertyId","createdAt")
        VALUES (%s,%s,NOW())
        ON CONFLICT ("userId","propertyId") DO NOTHING
    """, (uid, pid))

    conn.commit()
    print("❤️ Liked")

# =========================
def visit(uid, pid):

    if not validate_property(pid):
        print("❌ Invalid Property ID")
        return

    t = input("Visit (YYYY-MM-DD HH:MM): ").strip()

    try:
        visit_time = datetime.strptime(t, "%Y-%m-%d %H:%M")
    except ValueError:
        print("❌ Invalid format")
        return

    if visit_time <= datetime.now():
        print("❌ Past visit not allowed")
        return

    cursor.execute("""
        INSERT INTO "Visit"
        ("userId","propertyId","visitDateTime","status","createdAt")
        VALUES (%s,%s,%s,'pending',NOW())
    """, (uid, pid, visit_time))

    conn.commit()
    print("📅 Visit booked")

# =========================
def message(uid, pid, msg):

    if not validate_property(pid):
        print("❌ Invalid Property ID")
        return

    cursor.execute('SELECT "userId" FROM "Property" WHERE id=%s', (pid,))
    owner = cursor.fetchone()

    if not owner:
        print("❌ Owner not found")
        return

    cursor.execute("""
        INSERT INTO "Message"
        (senderId,receiverId,propertyId,message,"createdAt")
        VALUES (%s,%s,%s,%s,NOW())
    """, (uid, owner[0], pid, msg))

    conn.commit()
    print("💬 Sent")

# =========================
def add_property(uid):

    print("\n🏠 SELLER FORM")

    data = {}

    for field, typ, optional in SELLER_SCHEMA:

        while True:
            val = input(f"{field}: ")

            if optional and val == "":
                data[field] = None
                break

            if val == "":
                print("Required ❌")
                continue

            try:
                data[field] = float(val) if typ == float else val
                break
            except:
                print("Invalid ❌")

    cursor.execute("""
        INSERT INTO "Property"
        ("userId",city,locality,street,landmark,
         latitude,longitude,"propertyName","propertyType",
         parking,"createdAt","updatedAt")
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
    """, (
        uid,
        data["city"],
        data["locality"],
        data["street"],
        data["landmark"],
        data["latitude"],
        data["longitude"],
        data["propertyName"],
        data["propertyType"],
        data["parking"]
    ))

    conn.commit()
    print("✅ Property added")

# =========================
# AI (FIXED - NO SQL / NO DB TALK)
# =========================
history = []

def ai(msg, props):

    context = "\n".join([
        f"""
ID: {p[0]}
City: {p[1]}
Locality: {p[2]}
Name: {p[3]}
Type: {p[4]}
"""
        for p in props
    ])

    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": """
You are a real estate assistant chatbot.

STRICT RULES:
-Use only DB data. No hallucination
- NEVER write SQL queries
- NEVER mention database, tables, or schema
- NEVER explain backend logic
- NEVER output code
- ONLY use provided property data
- Always respond in natural human conversation
- If data is missing, say "not available"
"""
            },
            *history[-5:],
            {"role": "user", "content": msg + "\n\nProperties:\n" + context}
        ]
    )

    reply = res.choices[0].message.content

    history.append({"role": "user", "content": msg})
    history.append({"role": "assistant", "content": reply})

    return reply

# =========================
# MAIN
# =========================
role = select_role()
uid, city = register_user()

print("\nSYSTEM STARTED\n")

while True:

    msg = input("You: ")

    if msg.strip().lower() == "exit":
        break

    props = search(city)

    for p in props:
        save_view(uid, p[0])

    print("\nAI:", ai(msg, props), "\n")

    if role == "buyer":
        if "like" in msg.lower():
            like(uid, int(input("Property ID: ")))

        if "visit" in msg.lower():
            visit(uid, int(input("Property ID: ")))

        if "message" in msg.lower():
            message(uid, int(input("Property ID: ")), msg)

    if role == "seller":
        if "add" in msg.lower():
            add_property(uid)

cursor.close()
conn.close()
print("Closed")