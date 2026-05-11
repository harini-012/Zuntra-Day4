import os
import json
import psycopg2
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
import cloudinary
import cloudinary.uploader

# =========================
# ENV
# =========================
load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# =========================
# CLOUDINARY
# =========================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# =========================
# DB CONNECTION
# =========================
conn = psycopg2.connect(
    os.getenv("DATABASE_URL"),
    sslmode="require"
)

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
# AI HISTORY
# =========================
history = []

# =========================
# ROLE
# =========================
def select_role():

    while True:

        print("\n1. Buyer")
        print("2. Seller")

        role = input("Role: ").strip()

        if role == "1":
            return "buyer"

        elif role == "2":
            return "seller"

        else:
            print("❌ Invalid role")

# =========================
# REGISTER USER
# =========================
def register_user():

    # MOBILE
    while True:

        mobile = input("Mobile: ").strip()

        if mobile == "":
            print("❌ Mobile required")
            continue

        if not mobile.isdigit():
            print("❌ Mobile must contain only numbers")
            continue

        if len(mobile) != 10:
            print("❌ Mobile must be 10 digits")
            continue

        break

    # NAME
    while True:

        name = input("Name: ").strip()

        if name == "":
            print("❌ Name required")
            continue

        if len(name) < 3:
            print("❌ Name too short")
            continue

        if not all(c.isalpha() or c.isspace() for c in name):
            print("❌ Name must contain only letters")
            continue

        break

    # CITY
    while True:

        city = input("City: ").strip().title()

        if city == "":
            print("❌ City required")
            continue

        if not all(c.isalpha() or c.isspace() for c in city):
            print("❌ Invalid city")
            continue

        break

    try:

        cursor.execute(
            'SELECT id FROM "User" WHERE mobile=%s',
            (mobile,)
        )

        user = cursor.fetchone()

        if user:
            print("✅ Existing User Login")
            return user[0], city

        cursor.execute("""
            INSERT INTO "User"
            (
                mobile,
                name,
                city,
                "createdAt"
            )
            VALUES
            (
                %s,
                %s,
                %s,
                NOW()
            )
            RETURNING id
        """, (
            mobile,
            name,
            city
        ))

        uid = cursor.fetchone()[0]

        conn.commit()

        print("✅ User Registered")

        return uid, city

    except Exception as e:

        conn.rollback()

        print("❌ Register Error")
        print(e)

# =========================
# SAVE CHAT
# =========================
def save_chat(uid, role, content):

    try:

        if content.strip() == "":
            return

        cursor.execute("""
            INSERT INTO "ChatMessage"
            (
                "userId",
                role,
                content,
                "createdAt"
            )
            VALUES
            (
                %s,
                %s,
                %s,
                NOW()
            )
        """, (
            uid,
            role,
            content
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()

        print("❌ Chat Save Error")
        print(e)

# =========================
# SEARCH PROPERTY
# =========================
def search(city):

    try:

        cursor.execute("""
            SELECT
                id,
                city,
                locality,
                "propertyName",
                "propertyType"
            FROM "Property"
            WHERE LOWER(TRIM(city))
            = LOWER(TRIM(%s))
            ORDER BY id DESC
            LIMIT 10
        """, (city,))

        return cursor.fetchall()

    except Exception as e:

        conn.rollback()

        print("❌ Search Error")
        print(e)

        return []

# =========================
# VALIDATE PROPERTY
# =========================
def validate_property(pid):

    try:

        cursor.execute(
            'SELECT id FROM "Property" WHERE id=%s',
            (pid,)
        )

        return cursor.fetchone() is not None

    except Exception as e:

        conn.rollback()

        print("❌ Validation Error")
        print(e)

        return False

# =========================
# SAVE VIEW
# =========================
def save_view(uid, pid):

    try:

        cursor.execute("""
            INSERT INTO "PropertyView"
            (
                "userId",
                "propertyId",
                "createdAt"
            )
            VALUES
            (
                %s,
                %s,
                NOW()
            )
            ON CONFLICT
            (
                "userId",
                "propertyId"
            )
            DO NOTHING
        """, (
            uid,
            pid
        ))

        conn.commit()

    except Exception as e:

        conn.rollback()

        print("❌ View Save Error")
        print(e)

# =========================
# LIKE PROPERTY
# =========================
def like(uid, pid):

    try:

        if not validate_property(pid):
            print("❌ Invalid Property ID")
            return

        cursor.execute("""
            INSERT INTO "Like"
            (
                "userId",
                "propertyId",
                "createdAt"
            )
            VALUES
            (
                %s,
                %s,
                NOW()
            )
            ON CONFLICT
            (
                "userId",
                "propertyId"
            )
            DO NOTHING
        """, (
            uid,
            pid
        ))

        conn.commit()

        print("❤️ Property Liked")

    except Exception as e:

        conn.rollback()

        print("❌ Like Error")
        print(e)

# =========================
# VISIT PROPERTY
# =========================
def visit(uid, pid):

    try:

        if not validate_property(pid):
            print("❌ Invalid Property ID")
            return

        t = input(
            "Visit Date & Time (YYYY-MM-DD HH:MM): "
        ).strip()

        try:

            visit_time = datetime.strptime(
                t,
                "%Y-%m-%d %H:%M"
            )

        except ValueError:

            print("❌ Invalid format")
            return

        if visit_time <= datetime.now():

            print("❌ Past visit not allowed")
            return

        cursor.execute("""
            INSERT INTO "Visit"
            (
                "userId",
                "propertyId",
                "visitDateTime",
                status,
                "createdAt"
            )
            VALUES
            (
                %s,
                %s,
                %s,
                'pending',
                NOW()
            )
        """, (
            uid,
            pid,
            visit_time
        ))

        conn.commit()

        print("📅 Visit booked")

    except Exception as e:

        conn.rollback()

        print("❌ Visit Error")
        print(e)

# =========================
# MESSAGE OWNER
# =========================
def message(uid):

    try:

        pid_input = input("Property ID: ").strip()

        if not pid_input.isdigit():
            print("❌ Property ID must be number")
            return

        pid = int(pid_input)

        if not validate_property(pid):
            print("❌ Invalid Property ID")
            return

        msg = input("Message: ").strip()

        if msg == "":
            print("❌ Message required")
            return

        if len(msg) > 500:
            print("❌ Message too long")
            return

        cursor.execute(
            'SELECT "userId" FROM "Property" WHERE id=%s',
            (pid,)
        )

        owner = cursor.fetchone()

        if not owner:
            print("❌ Owner not found")
            return

        receiver_id = owner[0]

        if receiver_id == uid:
            print("❌ Cannot message your own property")
            return

        cursor.execute("""
            INSERT INTO "Message"
            (
                "senderId",
                "receiverId",
                "propertyId",
                "message",
                "createdAt"
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                NOW()
            )
        """, (
            uid,
            receiver_id,
            pid,
            msg
        ))

        conn.commit()

        print("💬 Message Sent")

    except Exception as e:

        conn.rollback()

        print("❌ Message Error")
        print(e)

# =========================
# ADD PROPERTY
# =========================
def add_property(uid):

    print("\n🏠 SELLER FORM")

    data = {}

    for field, typ, optional in SELLER_SCHEMA:

        while True:

            val = input(f"{field}: ").strip()

            # OPTIONAL
            if optional and val == "":
                data[field] = None
                break

            # REQUIRED
            if val == "":
                print(f"❌ {field} required")
                continue

            try:

                if typ == float:

                    number = float(val)

                    if field == "latitude":

                        if number < -90 or number > 90:
                            print("❌ Invalid latitude")
                            continue

                    if field == "longitude":

                        if number < -180 or number > 180:
                            print("❌ Invalid longitude")
                            continue

                    data[field] = number

                else:

                    if len(val) < 2:
                        print(f"❌ Invalid {field}")
                        continue

                    data[field] = val

                break

            except:

                print(f"❌ Invalid {field}")

    try:

        cursor.execute("""
            INSERT INTO "Property"
            (
                "userId",
                city,
                locality,
                street,
                landmark,
                latitude,
                longitude,
                "propertyName",
                "propertyType",
                parking,
                "createdAt",
                "updatedAt"
            )
            VALUES
            (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                NOW(),NOW()
            )
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

        print("✅ Property Added")

    except Exception as e:

        conn.rollback()

        print("❌ Property Add Error")
        print(e)

# =========================
# GENERATE PROPERTY AD
# =========================
def generate_ad():

    try:

        cursor.execute("""
            SELECT
                id,
                city,
                locality,
                "propertyName",
                "propertyType"
            FROM "Property"
            ORDER BY id DESC
        """)

        props = cursor.fetchall()

        if len(props) == 0:

            print("❌ No properties found")
            return

        print("\n🏠 AVAILABLE PROPERTIES\n")

        for p in props:

            print("--------------------------------")
            print("Property ID :", p[0])
            print("City        :", p[1])
            print("Locality    :", p[2])
            print("Name        :", p[3])
            print("Type        :", p[4])

        pid = input("\nEnter Property ID: ").strip()

        if not pid.isdigit():

            print("❌ Invalid Property ID")
            return

        pid = int(pid)

        cursor.execute("""
            SELECT
                city,
                locality,
                "propertyName",
                "propertyType",
                parking
            FROM "Property"
            WHERE id=%s
        """, (pid,))

        prop = cursor.fetchone()

        if not prop:

            print("❌ Property not found")
            return

        image_path = input("Enter Image Path: ").strip()

        upload = cloudinary.uploader.upload(
            image_path
        )

        image_url = upload["secure_url"]

        print("\n✅ Image Uploaded Successfully")

        prompt = f"""
Create a professional real estate advertisement.

Property Name: {prop[2]}
City: {prop[0]}
Locality: {prop[1]}
Property Type: {prop[3]}
Parking: {prop[4]}

Rules:
- Professional tone
- Short advertisement
- Mention locality
- Mention property type
- Add attractive ending
- Do NOT use placeholders
"""

        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.5,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        ad = res.choices[0].message.content

        print("\n🏠 GENERATED AD\n")
        print(ad)

        print("\n📸 IMAGE URL")
        print(image_url)

    except Exception as e:

        print("❌ Generate Ad Error")
        print(e)

# =========================
# MOVE IN ASSISTANT
# =========================
def move_in_assistant(selected_property):

    suggestions = []

    p = selected_property["data"]

    if not p:
        return "❌ No property selected"

    city = p[1]
    locality = p[2]
    property_type = str(p[4]).lower()

    suggestions.append("🧹 Deep clean before moving in")
    suggestions.append(f"📍 Location check: {locality}, {city}")

    if "pg" in property_type:

        suggestions.append("🛏️ Check shared washroom and WiFi availability")
        suggestions.append("🔐 Keep valuables secure")
        suggestions.append("📋 Ask about visitor rules")

    elif "1bhk" in property_type:

        suggestions.append("🪑 Use compact furniture")
        suggestions.append("🧺 Plan storage racks")
        suggestions.append("💡 Check ventilation")

    elif "2bhk" in property_type:

        suggestions.append("🛋️ Plan furniture layout")
        suggestions.append("📦 Separate boxes room-wise")
        suggestions.append("✔️ Great for families or roommates")

    elif "3bhk" in property_type:

        suggestions.append("🛏️ Assign rooms before shifting")
        suggestions.append("📺 Plan appliance placement")
        suggestions.append("🚚 Use larger transport vehicle")

    elif "villa" in property_type:

        suggestions.append("🌳 Inspect garden area")
        suggestions.append("🚗 Verify parking security")
        suggestions.append("💧 Check water system")

    else:

        suggestions.append("🏠 Verify property condition")

    return (
        "\n🏠 MOVE-IN ASSISTANT\n\n"
        + "\n".join(["• " + s for s in suggestions])
    )

# =========================
# AI CHAT
# =========================
def ai(msg, props):

    if len(props) == 0:

        context = "No properties available"

    else:

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

    try:

        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.2,
            messages=[

                {
                    "role": "system",
                    "content": """
You are a real estate assistant chatbot.

STRICT RULES:
- Use only provided property data
- No hallucination
- Never write SQL
- Never mention database
- Keep replies short
"""
                },

                *history[-5:],

                {
                    "role": "user",
                    "content":
                    msg + "\n\nProperties:\n" + context
                }
            ]
        )

        reply = res.choices[0].message.content

        history.append({
            "role": "user",
            "content": msg
        })

        history.append({
            "role": "assistant",
            "content": reply
        })

        return reply

    except Exception as e:

        return f"❌ AI Error: {e}"
def roommate_preferences(uid):

    print("\n👥 ROOMMATE FORM\n")

    data = {}

    data["sleepTiming"] = input(
        "Sleep timing: "
    ).strip().lower()

    data["foodHabit"] = input(
        "Food habit: "
    ).strip().lower()

    data["smoking"] = input(
        "Smoking: "
    ).strip().lower()

    data["drinking"] = input(
        "Drinking: "
    ).strip().lower()

    data["guests"] = input(
        "Guests frequency: "
    ).strip().lower()

    data["occupation"] = input(
        "Working/student: "
    ).strip().lower()

    data["wakeUpTime"] = input(
    "Wake up early or late: "
    ).strip().lower()

    data["studyStyle"] = input(
        "Quiet study or group study: "
    ).strip().lower()

    data["musicHabit"] = input(
        "Music loud or earphones: "
    ).strip().lower()

    data["socialEnergy"] = input(
        "Introvert or extrovert: "
    ).strip().lower()

    data["cleaningFrequency"] = input(
        "Daily cleaning or weekly cleaning: "
    ).strip().lower()

    data["workSchedule"] = input(
        "Day shift or night shift: "
    ).strip().lower()

    data["petFriendly"] = input(
        "Pet friendly yes/no: "
    ).strip().lower()

    data["sharingComfort"] = input(
        "Comfortable sharing items? "
    ).strip().lower()


    data["friendVisits"] = input(
        "Friends visit often or rarely: "
    ).strip().lower()

    data["cookingHabit"] = input(
        "Cook regularly or outside food: "
    ).strip().lower()

    data["roomVibe"] = input(
        "Calm vibe or energetic vibe: "
    ).strip().lower()

    try:

        cursor.execute("""

            INSERT INTO "UserPreference"
            (
                "userId",
                "sharingTypes",
                "createdAt",
                "updatedAt"
            )

            VALUES
            (
                %s,
                %s,
                NOW(),
                NOW()
            )

        """, (
            uid,
            json.dumps(data)
        ))

        conn.commit()

        print("✅ Preferences Saved")
        print("🎯 You can now type: find matches")

    except Exception as e:

        conn.rollback()

        print("❌ Error")
        print(e)
def find_matches(uid):

    try:

        # current user preference
        cursor.execute("""
            SELECT "sharingTypes"
            FROM "UserPreference"
            WHERE "userId"=%s
            ORDER BY id DESC
            LIMIT 1
        """, (uid,))

        current = cursor.fetchone()

        if not current:
            print("❌ Complete roommate form first")
            return

        current_data = current[0]

        if isinstance(current_data, str):
            current_data = json.loads(current_data)

        if isinstance(current_data, list):
            current_data = current_data[0]

        if not isinstance(current_data, dict):
            current_data = {}

        # 🔥 IMPORTANT CHANGE: join User table to get name/mobile
        cursor.execute("""
            SELECT 
                u.id,
                u.name,
                u.mobile,
                p."sharingTypes"
            FROM "UserPreference" p
            JOIN "User" u ON u.id = p."userId"
            WHERE u.id != %s
        """, (uid,))

        others = cursor.fetchall()

        print("\n👥 COMPATIBLE ROOMMATES\n")

        found = False

        for row in others:

            other_uid = row[0]
            name = row[1]
            mobile = row[2]
            other_data = row[3]

            if isinstance(other_data, str):
                other_data = json.loads(other_data)

            if isinstance(other_data, list):
                other_data = other_data[0]

            if not isinstance(other_data, dict):
                continue

            score = 0

            if current_data.get("sleepTiming") == other_data.get("sleepTiming"):
                score += 2

            if current_data.get("foodHabit") == other_data.get("foodHabit"):
                score += 1

            if current_data.get("smoking") == other_data.get("smoking"):
                score += 2

            if current_data.get("occupation") == other_data.get("occupation"):
                score += 2

            if score >= 5:

                found = True

                print("--------------------------------")
                print("Name   :", name)
                print("Mobile :", mobile)
                print("User ID:", other_uid)
                print("Score  :", score)

                if score >= 8:
                    print("Prediction: 🌟 Low conflict match")

                elif score >= 6:
                    print("Prediction: 📚 Good study environment")

                else:
                    print("Prediction: 🎉 Party-friendly group")

        if not found:
            print("❌ No compatible roommates found")

    except Exception as e:
        conn.rollback()
        print("❌ Match Error")
        print(e)
# =========================
# MAIN
# =========================
role = select_role()

uid, city = register_user()

print("\n✅ SYSTEM STARTED\n")

selected_property = {
    "data": None
}

move_in_keywords = [
    "move in",
    "ready to move",
    "i am ready to move",
    "iam ready to move",
    "finalized house",
    "i finalized the house"
]

while True:

    msg = input("You: ").strip()

    if msg == "":
        print("❌ Empty message not allowed")
        continue

    lower_msg = msg.lower()

    if lower_msg == "exit":
        break

    # =========================
    # SAVE USER CHAT
    # =========================
    save_chat(uid, "user", msg)

    # =========================
    # PROPERTY SEARCH
    # =========================
    props = search(city)

    for p in props:
        save_view(uid, p[0])

    # =========================
    # SELLER ACTIONS
    # =========================
    if role == "seller":

        if "add" in lower_msg:

            add_property(uid)
            continue

    # =========================
    # BUYER ACTIONS
    # =========================
    if role == "buyer":

        if "like" in lower_msg:

            pid = input("Property ID: ").strip()

            if pid.isdigit():
                like(uid, int(pid))

            continue

        if "visit" in lower_msg:

            pid = input("Property ID: ").strip()

            if pid.isdigit():
                visit(uid, int(pid))

            continue

        if "message" in lower_msg:

            message(uid)
            continue
    if "roomate" in lower_msg:

        roommate_preferences(uid)

        continue
    if "find matches" in lower_msg:

        find_matches(uid)

        continue
    # =========================
    # GENERATE AD
    # =========================
    if "generate ad" in lower_msg or "ad" in lower_msg:

        generate_ad()
        continue

    # =========================
    # SELLING TIPS
    # =========================
    if "selling tips" in lower_msg:

        tips = """

🏠 PROPERTY SELLING TIPS

1. Keep the property clean
2. Use good lighting for photos
3. Set competitive pricing
4. Highlight locality advantages
5. Mention parking and amenities
6. Upload quality images
7. Respond quickly to buyers
"""

        print(tips)

        save_chat(uid, "assistant", tips)

        continue

    # =========================
    # MOVE-IN MODE
    # =========================
    if any(k in lower_msg for k in move_in_keywords):

        pid = input(
            "Enter Property ID you finalized: "
        ).strip()

        if pid.isdigit():

            selected_property["data"] = next(
                (p for p in props if p[0] == int(pid)),
                None
            )

            if selected_property["data"]:

                reply = move_in_assistant(
                    selected_property
                )

            else:

                reply = "❌ Property not found"

        else:

            reply = "❌ Invalid Property ID"

        print("\nAI:", reply)

        save_chat(uid, "assistant", reply)

        continue

    # =========================
    # PROPERTY SEARCH KEYWORDS
    # =========================
    search_keywords = [
        "show property",
        "show properties",
        "property in",
        "properties in",
        "find property",
        "find properties"
    ]

    is_property_search = any(
        word in lower_msg
        for word in search_keywords
    )

    if is_property_search:

        search_city = city

        keywords = [
            "show property in",
            "show properties in",
            "property in",
            "properties in",
            "find property in",
            "find properties in"
        ]

        for key in keywords:

            if key in lower_msg:

                search_city = (
                    lower_msg.replace(key, "")
                    .strip()
                )

                break

        props = search(search_city)

        if len(props) == 0:

            reply = "\n❌ No matching properties found."

        else:

            reply = "\n🏠 AVAILABLE PROPERTIES\n"

            for p in props:

                reply += f"""
--------------------------------
Property ID : {p[0]}
City        : {p[1]}
Locality    : {p[2]}
Name        : {p[3]}
Type        : {p[4]}
"""

        print(reply)

        save_chat(uid, "assistant", reply)

        continue

    # =========================
    # DEFAULT AI CHAT
    # =========================
    reply = ai(msg, props)

    print("\nAI:", reply)

    save_chat(uid, "assistant", reply)

# =========================
# CLOSE
# =========================
cursor.close()
conn.close()

print("✅ Closed")
