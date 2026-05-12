import os
import json
import psycopg2
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
import cloudinary
import cloudinary.uploader

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

# =========================================
# FLASK
# =========================================
app = Flask(__name__)

# =========================================
# GROQ
# =========================================
client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# =========================================
# CLOUDINARY
# =========================================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# =========================================
# DATABASE
# =========================================
conn = psycopg2.connect(
    os.getenv("DATABASE_URL"),
    sslmode="require"
)

conn.autocommit = True
cursor = conn.cursor()

# =========================================
# CHAT HISTORY
# =========================================
history = []

# =========================================
# SAVE CHAT
# =========================================
def save_chat(uid, role, content):

    try:

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

    except Exception as e:
        print(e)

# =========================================
# REGISTER
# =========================================
@app.route("/register", methods=["POST"])
def register():

    try:

        data = request.json

        mobile = data["mobile"]
        name = data["name"]
        city = data["city"]

        cursor.execute(
            'SELECT id FROM "User" WHERE mobile=%s',
            (mobile,)
        )

        user = cursor.fetchone()

        if user:

            return jsonify({
                "message": "existing user",
                "userId": user[0]
            })

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

        return jsonify({
            "message": "registered",
            "userId": uid
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# ADD PROPERTY
# =========================================
@app.route("/add-property", methods=["POST"])
def add_property():

    try:

        data = request.json

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
            data["userId"],
            data["city"],
            data["locality"],
            data.get("street"),
            data.get("landmark"),
            data.get("latitude"),
            data.get("longitude"),
            data["propertyName"],
            data["propertyType"],
            data.get("parking")
        ))

        return jsonify({
            "message": "property added"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# PROPERTY SEARCH
# =========================================
@app.route("/properties", methods=["GET"])
def properties():

    try:

        city = request.args.get("city")

        cursor.execute("""
            SELECT
                id,
                city,
                locality,
                "propertyName",
                "propertyType"
            FROM "Property"
            WHERE LOWER(city)=LOWER(%s)
        """, (city,))

        rows = cursor.fetchall()

        return jsonify([
            {
                "propertyId": r[0],
                "city": r[1],
                "locality": r[2],
                "propertyName": r[3],
                "propertyType": r[4]
            }
            for r in rows
        ])

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# LIKE PROPERTY
# =========================================
@app.route("/like", methods=["POST"])
def like():

    try:

        data = request.json

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
            ON CONFLICT DO NOTHING
        """, (
            data["userId"],
            data["propertyId"]
        ))

        return jsonify({
            "message": "property liked"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# VISIT BOOKING
# =========================================
@app.route("/visit", methods=["POST"])
def visit():

    try:

        data = request.json

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
            data["userId"],
            data["propertyId"],
            data["visitDateTime"]
        ))

        return jsonify({
            "message": "visit booked"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# MESSAGE OWNER
# =========================================
@app.route("/message", methods=["POST"])
def message_owner():

    try:

        data = request.json

        cursor.execute(
            'SELECT "userId" FROM "Property" WHERE id=%s',
            (data["propertyId"],)
        )

        owner = cursor.fetchone()

        if not owner:

            return jsonify({
                "error": "owner not found"
            })

        receiver_id = owner[0]

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
            data["senderId"],
            receiver_id,
            data["propertyId"],
            data["message"]
        ))

        return jsonify({
            "message": "message sent"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# ROOMMATE PREFERENCES
# =========================================
@app.route("/roommate", methods=["POST"])
def roommate():

    try:

        data = request.json

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
            data["userId"],
            json.dumps(data["preferences"])
        ))

        return jsonify({
            "message": "preferences saved"
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# FIND MATCHES
# =========================================
@app.route("/matches/<int:uid>", methods=["GET"])
def matches(uid):

    try:

        # =====================================
        # GET CURRENT USER PREFERENCES
        # =====================================
        cursor.execute("""
            SELECT "sharingTypes"
            FROM "UserPreference"
            WHERE "userId"=%s
            ORDER BY id DESC
            LIMIT 1
        """, (uid,))

        current = cursor.fetchone()

        if not current:

            return jsonify({
                "error": "preferences not found"
            }), 404

        current_data = current[0]

        # =====================================
        # SAFE JSON CONVERSION
        # =====================================
        if isinstance(current_data, str):
            current_data = json.loads(current_data)

        if isinstance(current_data, list):
            current_data = current_data[0]

        if not isinstance(current_data, dict):
            current_data = {}

        # =====================================
        # GET OTHER USERS
        # =====================================
        cursor.execute("""
            SELECT
                u.id,
                u.name,
                u.mobile,
                p."sharingTypes"
            FROM "UserPreference" p
            JOIN "User" u
            ON u.id = p."userId"
            WHERE u.id != %s
        """, (uid,))

        rows = cursor.fetchall()

        results = []

        # =====================================
        # MATCH CALCULATION
        # =====================================
        for row in rows:

            other_data = row[3]

            # SAFE JSON CONVERSION
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
                score += 2

            if current_data.get("smoking") == other_data.get("smoking"):
                score += 2

            if current_data.get("drinking") == other_data.get("drinking"):
                score += 2

            if current_data.get("occupation") == other_data.get("occupation"):
                score += 2

            if current_data.get("petFriendly") == other_data.get("petFriendly"):
                score += 2

            if current_data.get("cleaningFrequency") == other_data.get("cleaningFrequency"):
                score += 2

            # =====================================
            # ADD MATCH
            # =====================================
            if score >= 5:

                results.append({
                    "userId": row[0],
                    "name": row[1],
                    "mobile": row[2],
                    "score": score
                })

        # =====================================
        # SORT MATCHES
        # =====================================
        results.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return jsonify(results)

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# GENERATE ADVERTISEMENT
# =========================================
@app.route("/generate-ad", methods=["POST"])
def generate_ad():

    try:

        data = request.json

        property_id = data["propertyId"]
        image_path = data["imagePath"]

        cursor.execute("""
            SELECT
                city,
                locality,
                "propertyName",
                "propertyType",
                parking
            FROM "Property"
            WHERE id=%s
        """, (property_id,))

        prop = cursor.fetchone()

        if not prop:

            return jsonify({
                "error": "property not found"
            })

        upload = cloudinary.uploader.upload(image_path)

        image_url = upload["secure_url"]

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

        return jsonify({
            "advertisement": ad,
            "imageUrl": image_url
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# MOVE-IN ASSISTANT
# =========================================
@app.route("/move-in/<int:pid>", methods=["GET"])
def move_in(pid):

    try:

        cursor.execute("""
            SELECT
                city,
                locality,
                "propertyName",
                "propertyType"
            FROM "Property"
            WHERE id=%s
        """, (pid,))

        p = cursor.fetchone()

        if not p:

            return jsonify({
                "error": "property not found"
            })

        property_type = str(p[3]).lower()

        suggestions = []

        suggestions.append("Deep clean before moving")
        suggestions.append(f"Check locality {p[1]}, {p[0]}")

        if "pg" in property_type:
            suggestions.append("Check WiFi and shared washroom")

        elif "1bhk" in property_type:
            suggestions.append("Use compact furniture")

        elif "2bhk" in property_type:
            suggestions.append("Plan room-wise shifting")

        elif "villa" in property_type:
            suggestions.append("Inspect parking and garden")

        return jsonify({
            "moveInSuggestions": suggestions
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# AI CHAT
# =========================================
@app.route("/chat", methods=["POST"])
def chat():

    try:

        data = request.json

        uid = data["userId"]
        msg = data["message"]
        city = data.get("city", "Chennai")

        save_chat(uid, "user", msg)

        cursor.execute("""
            SELECT
                id,
                city,
                locality,
                "propertyName",
                "propertyType"
            FROM "Property"
            WHERE LOWER(city)=LOWER(%s)
        """, (city,))

        props = cursor.fetchall()

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
You are a real estate chatbot.

Rules:
- Use only given property data
- Keep answers short
- No hallucinations
"""
                },

                {
                    "role": "user",
                    "content": msg + "\n\nProperties:\n" + context
                }
            ]
        )

        reply = res.choices[0].message.content

        save_chat(uid, "assistant", reply)

        return jsonify({
            "reply": reply
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# RUN
# =========================================
if __name__ == "__main__":

    app.run(debug=True)
