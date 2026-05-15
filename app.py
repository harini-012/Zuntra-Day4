import os
import json
import psycopg2
import requests

from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq
from flask_cors import CORS
from datetime import datetime
from gtts import gTTS
import uuid
from flask import Flask, render_template
import cloudinary
import cloudinary.uploader
from langdetect import detect
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

# =========================================
# LOAD ENV
# =========================================
load_dotenv()

# =========================================
# FLASK
# =========================================
app = Flask(__name__)
CORS(app)
@app.route("/")
def home():
    return render_template("add.html")

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
# PINECONE
# =========================================
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX"))

# =========================================
# EMBEDDING MODEL
# =========================================
embed_model = SentenceTransformer(
    "BAAI/bge-large-en-v1.5"
)

def create_embedding(text):
    return embed_model.encode(text).tolist()

# =========================================
# DATABASE
# =========================================
conn = psycopg2.connect(
    os.getenv("DATABASE_URL"),
    sslmode="require"
)

conn.autocommit = True
cursor = conn.cursor()
VOICE_LANG_MAP = {
    "ENGLISH": "en",
    "HINDI": "hi",
    "TAMIL": "ta",
    "TELUGU": "te",
    "KANNADA": "kn"
}


@app.route("/check-user/<int:uid>", methods=["GET"])
def check_user(uid):

    try:

        cursor.execute(
            'SELECT id FROM "User" WHERE id=%s',
            (uid,)
        )

        user = cursor.fetchone()

        if user:

            return jsonify({
                "exists": True
            })

        else:

            return jsonify({
                "exists": False
            })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500
# =========================================
# VOICE REPLY
# =========================================

@app.route("/voice-reply", methods=["POST"])
def voice_reply():

    try:

        data = request.json

        uid = data["userId"]
        msg = data["message"]

        print("USER:", uid)
        print("MESSAGE:", msg)

        # =====================================
        # CHECK USER EXISTS
        # =====================================

        cursor.execute(
            'SELECT id,name FROM "User" WHERE id=%s',
            (uid,)
        )

        existing_user = cursor.fetchone()

        if not existing_user:

            return jsonify({
                "error": "invalid user"
            }), 404

        # =====================================
        # LANGUAGE DETECTION
        # =====================================

        user_language = detect_language(msg)

        save_chat(uid, "user", msg)

        context = ""

        # =====================================
        # VISIT KEYWORDS
        # =====================================

        visit_keywords = [

            "visit",
            "visits",
            "visited",
            "booked visit",
            "scheduled visit",
            "my visits",
            "visit history",
            "confirmed visit",
            "cancel visit",
            "next visit",
            "upcoming visit"

        ]

        # =====================================
        # VISIT ASSISTANT
        # =====================================

        if any(word in msg.lower() for word in visit_keywords):

            # =====================================
            # CANCEL VISIT
            # =====================================

            if "cancel" in msg.lower():

                cursor.execute("""

                    UPDATE "Visit"

                    SET status='cancelled'

                    WHERE id=(

                        SELECT id
                        FROM "Visit"

                        WHERE
                            "userId"=%s
                            AND status!='cancelled'

                        ORDER BY "visitDateTime" DESC

                        LIMIT 1
                    )

                """, (uid,))

                context = "Latest visit cancelled."

            # =====================================
            # CONFIRMED VISITS
            # =====================================

            elif "confirmed" in msg.lower():

                cursor.execute("""

                    SELECT
                        p."propertyName",
                        p.city,
                        p.locality,
                        p."propertyType",
                        v."visitDateTime",
                        v.status

                    FROM "Visit" v

                    JOIN "Property" p
                    ON p.id = v."propertyId"

                    WHERE
                        v."userId"=%s
                        AND v.status='confirmed'

                    ORDER BY v."visitDateTime" ASC

                """, (uid,))

                rows = cursor.fetchall()

                if rows:

                    for r in rows:

                        context += f"""
Property: {r[0]}
City: {r[1]}
Locality: {r[2]}
Type: {r[3]}
Visit Time: {r[4]}
Status: {r[5]}
"""

                else:

                    context = "No confirmed visits found."

            # =====================================
            # NEXT VISIT
            # =====================================

            elif "next" in msg.lower() or "upcoming" in msg.lower():

                cursor.execute("""

                    SELECT
                        p."propertyName",
                        p.city,
                        p.locality,
                        p."propertyType",
                        v."visitDateTime",
                        v.status

                    FROM "Visit" v

                    JOIN "Property" p
                    ON p.id = v."propertyId"

                    WHERE
                        v."userId"=%s
                        AND v."visitDateTime" >= NOW()

                    ORDER BY v."visitDateTime" ASC

                    LIMIT 1

                """, (uid,))

                rows = cursor.fetchall()

                if rows:

                    for r in rows:

                        context += f"""
Property: {r[0]}
City: {r[1]}
Locality: {r[2]}
Type: {r[3]}
Visit Time: {r[4]}
Status: {r[5]}
"""

                else:

                    context = "No upcoming visits found."

            # =====================================
            # VISITS IN CHENNAI
            # =====================================

            elif "chennai" in msg.lower():

                cursor.execute("""

                    SELECT
                        p."propertyName",
                        p.city,
                        p.locality,
                        p."propertyType",
                        v."visitDateTime",
                        v.status

                    FROM "Visit" v

                    JOIN "Property" p
                    ON p.id = v."propertyId"

                    WHERE
                        v."userId"=%s
                        AND LOWER(p.city)='chennai'

                    ORDER BY v."visitDateTime" DESC

                """, (uid,))

                rows = cursor.fetchall()

                if rows:

                    for r in rows:

                        context += f"""
Property: {r[0]}
City: {r[1]}
Locality: {r[2]}
Type: {r[3]}
Visit Time: {r[4]}
Status: {r[5]}
"""

                else:

                    context = "No Chennai visits found."

            # =====================================
            # ALL VISITS
            # =====================================

            else:

                cursor.execute("""

                    SELECT
                        p."propertyName",
                        p.city,
                        p.locality,
                        p."propertyType",
                        v."visitDateTime",
                        v.status

                    FROM "Visit" v

                    JOIN "Property" p
                    ON p.id = v."propertyId"

                    WHERE v."userId"=%s

                    ORDER BY v."visitDateTime" DESC

                """, (uid,))

                rows = cursor.fetchall()

                if rows:

                    for r in rows:

                        context += f"""
Property: {r[0]}
City: {r[1]}
Locality: {r[2]}
Type: {r[3]}
Visit Time: {r[4]}
Status: {r[5]}
"""

                else:

                    context = "No visited properties found."

        # =====================================
        # PROPERTY RECOMMENDATION ASSISTANT
        # =====================================

        else:

            smart_query = msg.lower()

            # =====================================
            # SMART FILTERS
            # =====================================

            if "girls" in smart_query:
                smart_query += " girls pg"

            if "boys" in smart_query:
                smart_query += " boys pg"

            if "food" in smart_query:
                smart_query += " food included"

            if "2bhk" in smart_query:
                smart_query += " 2bhk"

            if "1bhk" in smart_query:
                smart_query += " 1bhk"

            if "chennai" in smart_query:
                smart_query += " chennai"

            # =====================================
            # USER PREFERENCE MATCHING
            # =====================================

            cursor.execute("""

                SELECT
                    city,
                    locality,
                    "preferredTenant",
                    "foodIncluded",
                    "rentMin",
                    "rentMax"

                FROM "UserPreference"

                WHERE "userId"=%s

                ORDER BY id DESC

                LIMIT 1

            """, (uid,))

            pref = cursor.fetchone()

            if pref:

                if pref[0]:
                    smart_query += f" {pref[0]}"

                if pref[1]:
                    smart_query += f" {pref[1]}"

                if pref[2]:
                    smart_query += f" {pref[2]}"

                if pref[3]:
                    smart_query += " food included"

            # =====================================
            # MCP PROPERTY SEARCH
            # =====================================

            results = call_mcp_tool(
                "search-properties",
                {
                    "query": smart_query
                }
            )

            # =====================================
            # BUILD PROPERTY CONTEXT
            # =====================================

            for m in results.get("matches", []):

                meta = m.get("metadata", {})

                context += f"""
Property: {meta.get('propertyName')}
City: {meta.get('city')}
Locality: {meta.get('locality')}
Type: {meta.get('propertyType')}
"""

            if context.strip() == "":
                context = "No matching properties found."

        # =====================================
        # AI RESPONSE
        # =====================================

        res = client.chat.completions.create(

            model="llama-3.1-8b-instant",

            temperature=0.2,

            messages=[

                {
                    "role": "system",
                    "content": f"""
You are a real estate voice assistant.

STRICT RULES:
- Respond ONLY in this language: {user_language}
- Do NOT mix languages
- Keep responses short (2–4 lines)
- Use ONLY provided property data
- Never hallucinate
- Be conversational and professional

Detected language: {user_language}
"""
                },

                {
                    "role": "user",
                    "content": f"""
User Query:
{msg}

Database Data:
{context}
"""
                }
            ]
        )

        reply = res.choices[0].message.content

        save_chat(uid, "assistant", reply)

        # =====================================
        # GENERATE VOICE
        # =====================================

        lang_code = VOICE_LANG_MAP.get(
            user_language,
            "en"
        )

        audio_url = generate_voice(
            reply,
            lang_code
        )

        # =====================================
        # FINAL RESPONSE
        # =====================================

        return jsonify({

            "reply": reply,
            "audio": audio_url,
            "language": user_language

        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500
def generate_voice(text, lang_code="en"):
    try:
        filename = f"voice_{uuid.uuid4()}.mp3"
        path = os.path.join("static", filename)

        os.makedirs("static", exist_ok=True)

        tts = gTTS(text=text, lang=lang_code)
        tts.save(path)

        return f"/static/{filename}"

    except Exception as e:
        print("VOICE ERROR:", e)
        return None
def detect_language(text):
    try:
        lang = detect(text)

        if lang == "ta":
            return "TAMIL"
        elif lang == "hi":
            return "HINDI"
        elif lang == "kn":
            return "KANNADA"
        elif lang == "te":
            return "TELUGU"
        else:
            return "ENGLISH"
    except:
        return "ENGLISH"

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
# MCP CLIENT
# =========================================
def call_mcp_tool(tool, payload):

    try:

        response = requests.post(
            f"http://127.0.0.1:5000/mcp/{tool}",
            json=payload,
            timeout=20
        )

        return response.json()

    except Exception as e:

        print("MCP ERROR:", e)

        return {
            "matches": []
        }

# =========================================
# MCP TOOL
# =========================================

@app.route("/mcp/search-properties", methods=["POST"])
def mcp_search_properties():

    print("🔥 MCP SEARCH TOOL EXECUTED")

    try:

        data = request.json

        query = data.get("query", "")

        vector = create_embedding(query)

        results = index.query(
            vector=vector,
            top_k=5,
            include_metadata=True,
            filter={
                "type": "property"
            }
        )

        matches = []

        for m in results.get("matches", []):

            matches.append({
                "id": m.get("id"),
                "score": float(m.get("score", 0)),
                "metadata": m.get("metadata", {})
            })

        return jsonify({
            "matches": matches
        })

    except Exception as e:

        print("MCP SEARCH ERROR:", e)

        return jsonify({
            "error": str(e),
            "matches": []
        }), 500

# =========================================
# MCP DB TOOL
# =========================================
@app.route("/mcp/get-properties-by-city", methods=["POST"])
def mcp_get_properties_by_city():

    print("🔥 MCP DB TOOL EXECUTED")

    try:

        data = request.json

        city = data.get("city")

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

        properties = []

        for r in rows:

            properties.append({
                "propertyId": r[0],
                "city": r[1],
                "locality": r[2],
                "propertyName": r[3],
                "propertyType": r[4]
            })

        return jsonify({
            "properties": properties
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# REGISTER
# =========================================
@app.route("/register", methods=["POST"])
def register():

    try:

        data = request.json

        cursor.execute(
            'SELECT id FROM "User" WHERE mobile=%s',
            (data["mobile"],)
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
            data["mobile"],
            data["name"],
            data["city"]
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
            RETURNING id
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

        property_id = cursor.fetchone()[0]

        # =====================================
        # VECTOR STORE INSERT
        # =====================================

        vector_text = f"""
        Property Name: {data['propertyName']}
        City: {data['city']}
        Locality: {data['locality']}
        Property Type: {data['propertyType']}
        """

        vector = create_embedding(vector_text)

        index.upsert(vectors=[{
            "id": str(property_id),
            "values": vector,
            "metadata": {
                "type": "property",
                "propertyId": property_id,
                "propertyName": data["propertyName"],
                "city": data["city"],
                "locality": data["locality"],
                "propertyType": data["propertyType"]
            }
        }])

        return jsonify({
            "message": "property added",
            "propertyId": property_id
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
            })

        current_data = current[0]

        # Convert JSON string safely
        if isinstance(current_data, str):
            current_data = json.loads(current_data)

        # Ensure dictionary
        if not isinstance(current_data, dict):
            return jsonify({
                "error": "invalid current user preferences format"
            }), 400

        rows = []

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

        for row in rows:

            other_data = row[3]

            if isinstance(other_data, str):
                other_data = json.loads(other_data)

            if not isinstance(other_data, dict):
                continue

            score = 0

            fields = [
                "sleepTiming",
                "foodHabit",
                "smoking",
                "drinking",
                "occupation",
                "petFriendly",
                "cleaningFrequency"
            ]

            for field in fields:

                if current_data.get(field) == other_data.get(field):
                    score += 2

            if score >= 5:

                results.append({
                    "userId": row[0],
                    "name": row[1],
                    "mobile": row[2],
                    "score": score
                })

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
# =========================================
# GENERATE ADVERTISEMENT
# =========================================
@app.route("/generate-ad", methods=["POST"])
def generate_ad():

    try:

        data = request.json

        # =====================================
        # FETCH PROPERTY + OWNER DETAILS
        # =====================================

        cursor.execute("""
            SELECT
                p.city,
                p.locality,
                p."propertyName",
                p."propertyType",
                p.parking,
                u.name,
                u.mobile
            FROM "Property" p
            JOIN "User" u
            ON p."userId" = u.id
            WHERE p.id=%s
        """, (data["propertyId"],))

        prop = cursor.fetchone()

        # =====================================
        # PROPERTY NOT FOUND
        # =====================================

        if not prop:

            return jsonify({
                "error": "No property found"
            }), 404

        # =====================================
        # CLOUDINARY IMAGE
        # =====================================

        upload = cloudinary.uploader.upload(
            data["imagePath"]
        )

        image_url = upload["secure_url"]

        # =====================================
        # AI PROMPT
        # =====================================

        prompt = f"""
Create a professional real estate advertisement.

Property Name: {prop[2]}
City: {prop[0]}
Locality: {prop[1]}
Property Type: {prop[3]}
Parking: {prop[4]}

Owner Name: {prop[5]}
Contact Number: {prop[6]}

Rules:
- Professional tone
- Attractive formatting
-Dont generate email
- Mention locality
- Mention contact information clearly
- Keep advertisement clean and short
"""

        # =====================================
        # GROQ AI
        # =====================================

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

        # =====================================
        # RESPONSE
        # =====================================

        return jsonify({

            "advertisement": ad,
            "imageUrl": image_url,
            "ownerName": prop[5],
            "mobile": prop[6]

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

        suggestions = [
            "Deep clean before moving",
            f"Check locality {p[1]}, {p[0]}",
            "Arrange electricity & water setup"
        ]

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
# AI CHAT WITH MCP
# =========================================
@app.route("/chat", methods=["POST"])
def chat():
    

    try:

        data = request.json

        uid = data["userId"]
        msg = data["message"]
        user_language = detect_language(msg)
        save_chat(uid, "user", msg)

        # =====================================
        # MCP SEARCH TOOL CALL
        # =====================================

        results = call_mcp_tool(
            "search-properties",
            {
                "query": msg
            }
        )

        print("MCP RESULTS:", results)

        # =====================================
        # BUILD CONTEXT
        # =====================================

        context = ""

        for m in results.get("matches", []):

            meta = m.get("metadata", {})

            context += f"""
Property: {meta.get('propertyName')}
City: {meta.get('city')}
Locality: {meta.get('locality')}
Type: {meta.get('propertyType')}
"""

        # =====================================
        # FALLBACK IF NO RESULTS
        # =====================================

        if context.strip() == "":
            context = "No matching properties found."

        # =====================================
        # AI RESPONSE
        # =====================================

        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.2,
            messages=[

                {
                     "role": "system",
    "content": f"""
You are a real estate chatbot.

IMPORTANT RULES:
- Respond ONLY in the user's language.
- Allowed languages: English, Tamil, Kannada, Hindi, Telugu

- Detected user language: {user_language}
-If user speaks in multiple languages,respond in the same multiple languages
- Use ONLY given property data.
- Keep answers short.
- Never hallucinate properties"""
                },

                {
                    "role": "user",
                    "content": f"""
User Query:
{msg}
Language:
{user_language}
Property Data:
{context}
"""
                }
            ]
        )

        reply = res.choices[0].message.content

        save_chat(uid, "assistant", reply)

        return jsonify({
            "reply": reply,
            "context": context
        })

    except Exception as e:

        print("CHAT ERROR:", e)

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# RUN
# =========================================
if __name__ == "__main__":

    app.run(debug=True)
