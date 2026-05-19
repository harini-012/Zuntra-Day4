import os
import json
import psycopg2
import requests

from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
from groq import Groq
from flask_cors import CORS
from datetime import datetime
from gtts import gTTS
import uuid
from flask import render_template
import cloudinary
import cloudinary.uploader
from langdetect import detect, LangDetectException
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
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route("/")
def home():
    return render_template("add.html")

# =========================================
# GROQ CLIENT
# =========================================
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
embed_model = SentenceTransformer("BAAI/bge-large-en-v1.5")

def create_embedding(text):
    return embed_model.encode(text).tolist()

# =========================================
# DATABASE — reconnect helper
# =========================================
_conn = None
_cursor = None

def get_cursor():
    global _conn, _cursor
    try:
        # ping to check if connection is alive
        _conn.cursor().execute("SELECT 1")
    except Exception:
        _conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
        _conn.autocommit = True
        _cursor = _conn.cursor()
    return _cursor

# initial connect
_conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
_conn.autocommit = True
_cursor = _conn.cursor()

# =========================================
# CONSTANTS
# =========================================
VOICE_LANG_MAP = {
    "ENGLISH": "en",
    "HINDI":   "hi",
    "TAMIL":   "ta",
    "TELUGU":  "te",
    "KANNADA": "kn"
}

VISIT_KEYWORDS = [
    "visit", "visits", "visited", "booked visit", "scheduled visit",
    "my visits", "visit history", "confirmed visit", "cancel visit",
    "next visit", "upcoming visit",
    # Hindi
    "मुलाकात", "भेंट", "विज़िट", "अपॉइंटमेंट",
    "मेरी विज़िट", "आगामी विज़िट", "विज़िट रद्द", "कन्फर्म विज़िट",
    # Tamil
    "சந்திப்பு", "பார்வை", "விசிட்", "என் விசிட்",
    "அடுத்த விசிட்", "வரவிருக்கும் விசிட்", "ரத்து செய் விசிட்",
    "உறுதி செய்யப்பட்ட விசிட்",
    # Telugu
    "సందర్శన", "విజిట్", "నా విజిట్స్", "తదుపరి విజిట్",
    "రద్దు విజిట్", "నిర్ధారిత విజిట్", "రాబోయే విజిట్",
    # Kannada
    "ಭೇಟಿ", "ವಿಜಿಟ್", "ನನ್ನ ಭೇಟಿಗಳು", "ಮುಂದಿನ ಭೇಟಿ",
    "ರದ್ದು ಭೇಟಿ", "ದೃಢೀಕೃತ ಭೇಟಿ", "ಬರುವ ಭೇಟಿ"
]

CANCEL_TOKENS  = ["cancel", "ரத்து", "रद्द", "రద్దు", "ರದ್ದು"]
CONFIRM_TOKENS = ["confirmed", "உறுதி", "कन्फर्म", "నిర్ధారిత", "ದೃಢೀಕೃತ"]
NEXT_TOKENS    = ["next", "upcoming", "அடுத்த", "வரவிருக்கும்",
                  "आगामी", "తదుపరి", "రాబోయే", "ಮುಂದಿನ", "ಬರುವ"]

# =========================================
# HELPERS
# =========================================

def detect_language(text: str) -> str:
    try:
        lang = detect(text)
        return {
            "ta": "TAMIL",
            "hi": "HINDI",
            "kn": "KANNADA",
            "te": "TELUGU"
        }.get(lang, "ENGLISH")
    except LangDetectException:
        return "ENGLISH"


def generate_voice(text: str, lang_code: str = "en"):
    try:
        os.makedirs("static", exist_ok=True)
        filename = f"voice_{uuid.uuid4()}.mp3"
        path = os.path.join("static", filename)
        gTTS(text=text, lang=lang_code).save(path)
        return f"/static/{filename}"
    except Exception as e:
        print("VOICE ERROR:", e)
        return None


def save_chat(uid: int, role: str, content: str):
    try:
        cur = get_cursor()
        cur.execute(
            """
            INSERT INTO "ChatMessage" ("userId", role, content, "createdAt")
            VALUES (%s, %s, %s, NOW())
            """,
            (uid, role, content)
        )
    except Exception as e:
        print("SAVE CHAT ERROR:", e)


def call_mcp_tool(tool: str, payload: dict) -> dict:
    try:
        res = requests.post(
            f"http://127.0.0.1:5000/mcp/{tool}",
            json=payload,
            timeout=20
        )
        return res.json()
    except Exception as e:
        print("MCP ERROR:", e)
        return {"matches": []}


def build_property_context(matches: list) -> str:
    ctx = ""
    for m in matches:
        meta = m.get("metadata", {})
        ctx += (
            f"\nProperty: {meta.get('propertyName')}"
            f"\nCity: {meta.get('city')}"
            f"\nLocality: {meta.get('locality')}"
            f"\nType: {meta.get('propertyType')}\n"
        )
    return ctx or "No matching properties found."


def build_visit_context(rows: list) -> str:
    if not rows:
        return ""
    ctx = ""
    for r in rows:
        ctx += (
            f"\nProperty: {r[0]}"
            f"\nCity: {r[1]}"
            f"\nLocality: {r[2]}"
            f"\nType: {r[3]}"
            f"\nVisit Time: {r[4]}"
            f"\nStatus: {r[5]}\n"
        )
    return ctx


def groq_reply(user_msg: str, context: str, language: str) -> str:
    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You are a real estate voice assistant.\n\n"
                    f"STRICT RULES:\n"
                    f"- Respond ONLY in this language: {language}\n"
                    f"- Do NOT mix languages\n"
                    f"- Keep responses short (2-4 lines)\n"
                    f"- Use ONLY the provided property/visit data\n"
                    f"- Never hallucinate\n"
                    f"- Be conversational and professional\n"
                    f"\nDetected language: {language}"
                )
            },
            {
                "role": "user",
                "content": f"User Query:\n{user_msg}\n\nDatabase Data:\n{context}"
            }
        ]
    )
    return res.choices[0].message.content


# =========================================
# CHECK USER
# =========================================
@app.route("/check-user/<int:uid>", methods=["GET"])
def check_user(uid):
    try:
        cur = get_cursor()
        cur.execute('SELECT id FROM "User" WHERE id=%s', (uid,))
        return jsonify({"exists": bool(cur.fetchone())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# REGISTER
# =========================================
@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.json
        cur = get_cursor()

        cur.execute('SELECT id FROM "User" WHERE mobile=%s', (data["mobile"],))
        user = cur.fetchone()

        if user:
            return jsonify({"message": "existing user", "userId": user[0]})

        cur.execute(
            """
            INSERT INTO "User" (mobile, name, city, "createdAt")
            VALUES (%s, %s, %s, NOW()) RETURNING id
            """,
            (data["mobile"], data["name"], data["city"])
        )
        uid = cur.fetchone()[0]
        return jsonify({"message": "registered", "userId": uid})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# VOICE REPLY  (main assistant endpoint)
# =========================================
@app.route("/voice-reply", methods=["POST"])
def voice_reply():
    try:
        data = request.json
        uid  = data["userId"]
        msg  = data["message"]

        cur = get_cursor()

        # -- validate user --
        cur.execute('SELECT id, name FROM "User" WHERE id=%s', (uid,))
        if not cur.fetchone():
            return jsonify({"error": "invalid user"}), 404

        user_language = detect_language(msg)
        save_chat(uid, "user", msg)
        msg_lower = msg.lower()
        context = ""

        # ============================================
        # BRANCH 1 — VISIT QUERIES
        # ============================================
        if any(kw in msg_lower for kw in VISIT_KEYWORDS):

            if any(t in msg_lower or t in msg for t in CANCEL_TOKENS):
                cur.execute(
                    """
                    UPDATE "Visit"
                    SET status='cancelled'
                    WHERE id=(
                        SELECT id FROM "Visit"
                        WHERE "userId"=%s AND status != 'cancelled'
                        ORDER BY "visitDateTime" DESC
                        LIMIT 1
                    )
                    """,
                    (uid,)
                )
                context = "Latest visit has been cancelled successfully."

            elif any(t in msg_lower or t in msg for t in CONFIRM_TOKENS):
                cur.execute(
                    """
                    SELECT p."propertyName", p.city, p.locality,
                           p."propertyType", v."visitDateTime", v.status
                    FROM "Visit" v
                    JOIN "Property" p ON p.id = v."propertyId"
                    WHERE v."userId"=%s AND v.status='confirmed'
                    ORDER BY v."visitDateTime" ASC
                    """,
                    (uid,)
                )
                context = build_visit_context(cur.fetchall()) or "No confirmed visits found."

            elif any(t in msg_lower or t in msg for t in NEXT_TOKENS):
                cur.execute(
                    """
                    SELECT p."propertyName", p.city, p.locality,
                           p."propertyType", v."visitDateTime", v.status
                    FROM "Visit" v
                    JOIN "Property" p ON p.id = v."propertyId"
                    WHERE v."userId"=%s AND v."visitDateTime" >= NOW()
                    ORDER BY v."visitDateTime" ASC
                    LIMIT 1
                    """,
                    (uid,)
                )
                context = build_visit_context(cur.fetchall()) or "No upcoming visits found."

            elif "chennai" in msg_lower:
                cur.execute(
                    """
                    SELECT p."propertyName", p.city, p.locality,
                           p."propertyType", v."visitDateTime", v.status
                    FROM "Visit" v
                    JOIN "Property" p ON p.id = v."propertyId"
                    WHERE v."userId"=%s AND LOWER(p.city)='chennai'
                    ORDER BY v."visitDateTime" DESC
                    """,
                    (uid,)
                )
                context = build_visit_context(cur.fetchall()) or "No Chennai visits found."

            else:
                cur.execute(
                    """
                    SELECT p."propertyName", p.city, p.locality,
                           p."propertyType", v."visitDateTime", v.status
                    FROM "Visit" v
                    JOIN "Property" p ON p.id = v."propertyId"
                    WHERE v."userId"=%s
                    ORDER BY v."visitDateTime" DESC
                    """,
                    (uid,)
                )
                context = build_visit_context(cur.fetchall()) or "No visited properties found."

        # ============================================
        # BRANCH 2 — PROPERTY RECOMMENDATION
        # ============================================
        else:
            smart_query = msg_lower

            # smart keyword expansion
            if "girls"   in smart_query: smart_query += " girls pg"
            if "boys"    in smart_query: smart_query += " boys pg"
            if "food"    in smart_query: smart_query += " food included"
            if "2bhk"    in smart_query: smart_query += " 2bhk"
            if "1bhk"    in smart_query: smart_query += " 1bhk"
            if "chennai" in smart_query: smart_query += " chennai"
            if "villa"   in smart_query: smart_query += " villa"
            if "studio"  in smart_query: smart_query += " studio apartment"
            if "cheap"   in smart_query: smart_query += " budget affordable"
            if "luxury"  in smart_query: smart_query += " luxury premium"

            # user preference boost
            cur.execute(
                """
                SELECT city, locality, "preferredTenant", "foodIncluded", "rentMin", "rentMax"
                FROM "UserPreference"
                WHERE "userId"=%s
                ORDER BY id DESC LIMIT 1
                """,
                (uid,)
            )
            pref = cur.fetchone()
            if pref:
                if pref[0]: smart_query += f" {pref[0]}"
                if pref[1]: smart_query += f" {pref[1]}"
                if pref[2]: smart_query += f" {pref[2]}"
                if pref[3]: smart_query += " food included"

            # vector search via MCP
            results = call_mcp_tool("search-properties", {"query": smart_query})
            context = build_property_context(results.get("matches", []))

        # ============================================
        # AI REPLY
        # ============================================
        reply = groq_reply(msg, context, user_language)
        save_chat(uid, "assistant", reply)

        lang_code = VOICE_LANG_MAP.get(user_language, "en")
        audio_url = generate_voice(reply, lang_code)

        return jsonify({
            "reply":    reply,
            "audio":    audio_url,
            "language": user_language,
            "context":  context
        })

    except Exception as e:
        print("VOICE REPLY ERROR:", e)
        return jsonify({"error": str(e)}), 500


# =========================================
# STATIC FILES (serve audio)
# =========================================
@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


# =========================================
# CHAT (text only, no voice)
# =========================================
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        uid  = data["userId"]
        msg  = data["message"]

        user_language = detect_language(msg)
        save_chat(uid, "user", msg)

        results = call_mcp_tool("search-properties", {"query": msg})
        context = build_property_context(results.get("matches", []))

        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a real estate chatbot.\n"
                        f"IMPORTANT RULES:\n"
                        f"- Respond ONLY in the user's language: {user_language}\n"
                        f"- If user uses multiple languages, reply in those same languages\n"
                        f"- Use ONLY given property data\n"
                        f"- Keep answers short\n"
                        f"- Never hallucinate properties"
                    )
                },
                {
                    "role": "user",
                    "content": f"User Query:\n{msg}\n\nProperty Data:\n{context}"
                }
            ]
        )
        reply = res.choices[0].message.content
        save_chat(uid, "assistant", reply)

        return jsonify({"reply": reply, "context": context})

    except Exception as e:
        print("CHAT ERROR:", e)
        return jsonify({"error": str(e)}), 500


# =========================================
# MCP — VECTOR SEARCH
# =========================================
@app.route("/mcp/search-properties", methods=["POST"])
def mcp_search_properties():
    print("MCP SEARCH TOOL EXECUTED")
    try:
        data  = request.json
        query = data.get("query", "")
        vector = create_embedding(query)

        results = index.query(
            vector=vector,
            top_k=5,
            include_metadata=True,
            filter={"type": "property"}
        )

        matches = [
            {
                "id":       m.get("id"),
                "score":    float(m.get("score", 0)),
                "metadata": m.get("metadata", {})
            }
            for m in results.get("matches", [])
        ]

        return jsonify({"matches": matches})

    except Exception as e:
        print("MCP SEARCH ERROR:", e)
        return jsonify({"error": str(e), "matches": []}), 500


# =========================================
# MCP — DB SEARCH BY CITY
# =========================================
@app.route("/mcp/get-properties-by-city", methods=["POST"])
def mcp_get_properties_by_city():
    print("MCP DB TOOL EXECUTED")
    try:
        city = request.json.get("city")
        cur  = get_cursor()
        cur.execute(
            """
            SELECT id, city, locality, "propertyName", "propertyType"
            FROM "Property"
            WHERE LOWER(city)=LOWER(%s)
            """,
            (city,)
        )
        rows = cur.fetchall()
        return jsonify({
            "properties": [
                {
                    "propertyId":   r[0],
                    "city":         r[1],
                    "locality":     r[2],
                    "propertyName": r[3],
                    "propertyType": r[4]
                }
                for r in rows
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# ADD PROPERTY
# =========================================
@app.route("/add-property", methods=["POST"])
def add_property():
    try:
        data = request.json
        cur  = get_cursor()

        cur.execute(
            """
            INSERT INTO "Property"
            ("userId", city, locality, street, landmark, latitude, longitude,
             "propertyName", "propertyType", parking, "createdAt", "updatedAt")
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
            RETURNING id
            """,
            (
                data["userId"],      data["city"],
                data["locality"],    data.get("street"),
                data.get("landmark"),data.get("latitude"),
                data.get("longitude"),data["propertyName"],
                data["propertyType"],data.get("parking")
            )
        )
        property_id = cur.fetchone()[0]

        vector_text = (
            f"Property Name: {data['propertyName']}\n"
            f"City: {data['city']}\n"
            f"Locality: {data['locality']}\n"
            f"Property Type: {data['propertyType']}"
        )
        vector = create_embedding(vector_text)

        index.upsert(vectors=[{
            "id":     str(property_id),
            "values": vector,
            "metadata": {
                "type":         "property",
                "propertyId":   property_id,
                "propertyName": data["propertyName"],
                "city":         data["city"],
                "locality":     data["locality"],
                "propertyType": data["propertyType"]
            }
        }])

        return jsonify({"message": "property added", "propertyId": property_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# PROPERTY SEARCH (by city)
# =========================================
@app.route("/properties", methods=["GET"])
def properties():
    try:
        city = request.args.get("city")
        cur  = get_cursor()
        cur.execute(
            """
            SELECT id, city, locality, "propertyName", "propertyType"
            FROM "Property"
            WHERE LOWER(city)=LOWER(%s)
            """,
            (city,)
        )
        rows = cur.fetchall()
        return jsonify([
            {
                "propertyId":   r[0],
                "city":         r[1],
                "locality":     r[2],
                "propertyName": r[3],
                "propertyType": r[4]
            }
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# LIKE PROPERTY
# =========================================
@app.route("/like", methods=["POST"])
def like():
    try:
        data = request.json
        cur  = get_cursor()
        cur.execute(
            """
            INSERT INTO "Like" ("userId", "propertyId", "createdAt")
            VALUES (%s, %s, NOW())
            ON CONFLICT DO NOTHING
            """,
            (data["userId"], data["propertyId"])
        )
        return jsonify({"message": "property liked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# VISIT BOOKING
# =========================================
@app.route("/visit", methods=["POST"])
def visit():
    try:
        data = request.json
        cur  = get_cursor()
        cur.execute(
            """
            INSERT INTO "Visit" ("userId", "propertyId", "visitDateTime", status, "createdAt")
            VALUES (%s, %s, %s, 'pending', NOW())
            """,
            (data["userId"], data["propertyId"], data["visitDateTime"])
        )
        return jsonify({"message": "visit booked"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# VISIT STATUS UPDATE
# =========================================
@app.route("/visit/<int:visit_id>/status", methods=["PATCH"])
def update_visit_status(visit_id):
    try:
        status = request.json.get("status")
        if status not in ("pending", "confirmed", "cancelled"):
            return jsonify({"error": "invalid status"}), 400
        cur = get_cursor()
        cur.execute(
            'UPDATE "Visit" SET status=%s WHERE id=%s',
            (status, visit_id)
        )
        return jsonify({"message": f"visit {status}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# MESSAGE OWNER
# =========================================
@app.route("/message", methods=["POST"])
def message_owner():
    try:
        data = request.json
        cur  = get_cursor()

        cur.execute('SELECT "userId" FROM "Property" WHERE id=%s', (data["propertyId"],))
        owner = cur.fetchone()
        if not owner:
            return jsonify({"error": "owner not found"}), 404

        cur.execute(
            """
            INSERT INTO "Message" ("senderId", "receiverId", "propertyId", "message", "createdAt")
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (data["senderId"], owner[0], data["propertyId"], data["message"])
        )
        return jsonify({"message": "message sent"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# ROOMMATE PREFERENCES
# =========================================
@app.route("/roommate", methods=["POST"])
def roommate():
    try:
        data = request.json
        cur  = get_cursor()
        cur.execute(
            """
            INSERT INTO "UserPreference" ("userId", "sharingTypes", "createdAt", "updatedAt")
            VALUES (%s, %s, NOW(), NOW())
            """,
            (data["userId"], json.dumps(data["preferences"]))
        )
        return jsonify({"message": "preferences saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# ROOMMATE MATCH
# =========================================
@app.route("/matches/<int:uid>", methods=["GET"])
def matches(uid):
    try:
        cur = get_cursor()
        cur.execute(
            """
            SELECT "sharingTypes" FROM "UserPreference"
            WHERE "userId"=%s ORDER BY id DESC LIMIT 1
            """,
            (uid,)
        )
        current = cur.fetchone()
        if not current:
            return jsonify({"error": "preferences not found"}), 404

        current_data = current[0]
        if isinstance(current_data, str):
            current_data = json.loads(current_data)
        if not isinstance(current_data, dict):
            return jsonify({"error": "invalid preferences format"}), 400

        cur.execute(
            """
            SELECT u.id, u.name, u.mobile, p."sharingTypes"
            FROM "UserPreference" p
            JOIN "User" u ON u.id = p."userId"
            WHERE u.id != %s
            """,
            (uid,)
        )

        FIELDS = ["sleepTiming", "foodHabit", "smoking", "drinking",
                  "occupation", "petFriendly", "cleaningFrequency"]

        results = []
        for row in cur.fetchall():
            other_data = row[3]
            if isinstance(other_data, str):
                other_data = json.loads(other_data)
            if not isinstance(other_data, dict):
                continue

            score = sum(
                2 for f in FIELDS
                if current_data.get(f) == other_data.get(f)
            )
            if score >= 5:
                results.append({
                    "userId": row[0],
                    "name":   row[1],
                    "mobile": row[2],
                    "score":  score
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return jsonify(results)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# GENERATE ADVERTISEMENT
# =========================================
@app.route("/generate-ad", methods=["POST"])
def generate_ad():
    try:
        data = request.json
        cur  = get_cursor()

        cur.execute(
            """
            SELECT p.city, p.locality, p."propertyName", p."propertyType",
                   p.parking, u.name, u.mobile
            FROM "Property" p
            JOIN "User" u ON p."userId" = u.id
            WHERE p.id=%s
            """,
            (data["propertyId"],)
        )
        prop = cur.fetchone()
        if not prop:
            return jsonify({"error": "No property found"}), 404

        upload    = cloudinary.uploader.upload(data["imagePath"])
        image_url = upload["secure_url"]

        prompt = (
            f"Create a professional real estate advertisement.\n\n"
            f"Property Name: {prop[2]}\n"
            f"City: {prop[0]}\n"
            f"Locality: {prop[1]}\n"
            f"Property Type: {prop[3]}\n"
            f"Parking: {prop[4]}\n\n"
            f"Owner Name: {prop[5]}\n"
            f"Contact Number: {prop[6]}\n\n"
            f"Rules:\n"
            f"- Professional and attractive tone\n"
            f"- Mention locality and property highlights\n"
            f"- Include contact information clearly\n"
            f"- Do NOT generate email address\n"
            f"- Keep it clean, concise, and under 150 words"
        )

        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}]
        )
        ad = res.choices[0].message.content

        return jsonify({
            "advertisement": ad,
            "imageUrl":      image_url,
            "ownerName":     prop[5],
            "mobile":        prop[6]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# MOVE-IN ASSISTANT
# =========================================
@app.route("/move-in/<int:pid>", methods=["GET"])
def move_in(pid):
    try:
        cur = get_cursor()
        cur.execute(
            'SELECT city, locality, "propertyName", "propertyType" FROM "Property" WHERE id=%s',
            (pid,)
        )
        p = cur.fetchone()
        if not p:
            return jsonify({"error": "property not found"}), 404

        ptype = str(p[3]).lower()
        suggestions = [
            "Deep clean the entire space before moving in",
            f"Explore the locality: {p[1]}, {p[0]}",
            "Arrange electricity, water and gas connections",
            "Document existing damage with photos",
            "Confirm rental agreement and deposit receipt"
        ]

        if "pg" in ptype:
            suggestions += [
                "Check shared WiFi speed and reliability",
                "Confirm washroom and kitchen sharing rules"
            ]
        elif "1bhk" in ptype:
            suggestions.append("Use compact multi-purpose furniture to save space")
        elif "2bhk" in ptype:
            suggestions.append("Plan room-wise shifting for smooth move")
        elif "villa" in ptype:
            suggestions += [
                "Inspect parking space and garden area",
                "Check boundary wall and security system"
            ]
        elif "studio" in ptype:
            suggestions.append("Opt for wall-mounted shelves to maximise floor space")

        return jsonify({"moveInSuggestions": suggestions})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# CHAT HISTORY
# =========================================
@app.route("/chat-history/<int:uid>", methods=["GET"])
def chat_history(uid):
    try:
        cur   = get_cursor()
        limit = request.args.get("limit", 50)
        cur.execute(
            """
            SELECT role, content, "createdAt"
            FROM "ChatMessage"
            WHERE "userId"=%s
            ORDER BY "createdAt" DESC
            LIMIT %s
            """,
            (uid, limit)
        )
        rows = cur.fetchall()
        return jsonify([
            {
                "role":      r[0],
                "content":   r[1],
                "createdAt": r[2].isoformat() if r[2] else None
            }
            for r in reversed(rows)
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================
# HEALTH CHECK
# =========================================
@app.route("/health", methods=["GET"])
def health():
    try:
        cur = get_cursor()
        cur.execute("SELECT 1")
        return jsonify({"status": "ok", "db": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "db": str(e)}), 500


# =========================================
# RUN
# =========================================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
