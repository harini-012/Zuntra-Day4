    import os
    import json
    import psycopg2
    from flask import Flask, request, jsonify
    from dotenv import load_dotenv
    from groq import Groq
    from datetime import datetime

    # =========================
    # INIT
    # =========================
    load_dotenv()

    app = Flask(__name__)

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # ✅ IMPORTANT FIX: prevent transaction chain failure
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
    conn.autocommit = True
    cursor = conn.cursor()

    # =========================
    # MATCH SCORE
    # =========================
    def calculate_score(a, b):

        if not a or not b:
            return 0

        keys = [
            "sleepTiming",
            "foodHabit",
            "smoking",
            "drinking",
            "occupation",
            "petFriendly",
            "cleaningFrequency"
        ]

        score = 0

        for k in keys:
            if a.get(k) == b.get(k):
                score += 2

        return score


    # =========================
    # REGISTER USER
    # =========================
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
                return jsonify({"message": "existing user", "userId": user[0]})

            cursor.execute("""
                INSERT INTO "User" (mobile, name, city, "createdAt")
                VALUES (%s, %s, %s, NOW())
                RETURNING id
            """, (mobile, name, city))

            uid = cursor.fetchone()[0]

            return jsonify({"message": "registered", "userId": uid})

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # =========================
    # ROOMMATE PREFERENCES
    # =========================
    @app.route("/roommate", methods=["POST"])
    def roommate():

        try:
            data = request.json
            uid = data["userId"]

            cursor.execute("""
                INSERT INTO "UserPreference"
                ("userId", "sharingTypes", "createdAt", "updatedAt")
                VALUES (%s, %s, NOW(), NOW())
            """, (
                uid,
                json.dumps(data["preferences"])
            ))

            return jsonify({"message": "preferences saved"})

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # =========================
    # FIND MATCHES
    # =========================
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
                return jsonify({"error": "No preferences found"})

            current_data = current[0]

            if isinstance(current_data, str):
                current_data = json.loads(current_data)

            cursor.execute("""
                SELECT u.id, u.name, u.mobile, p."sharingTypes"
                FROM "UserPreference" p
                JOIN "User" u ON u.id = p."userId"
                WHERE u.id != %s
            """, (uid,))

            rows = cursor.fetchall()

            results = []

            for r in rows:

                other_data = r[3]

                if isinstance(other_data, str):
                    other_data = json.loads(other_data)

                score = calculate_score(current_data, other_data)

                if score >= 5:
                    results.append({
                        "userId": r[0],
                        "name": r[1],
                        "mobile": r[2],
                        "score": score
                    })

            results.sort(key=lambda x: x["score"], reverse=True)

            return jsonify(results)

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # =========================
    # PROPERTY SEARCH
    # =========================
    @app.route("/properties", methods=["GET"])
    def properties():

        try:
            city = request.args.get("city")

            cursor.execute("""
                SELECT id, city, locality, "propertyName", "propertyType"
                FROM "Property"
                WHERE LOWER(city)=LOWER(%s)
            """, (city,))

            return jsonify(cursor.fetchall())

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # =========================
    # LIKE PROPERTY
    # =========================
    @app.route("/like", methods=["POST"])
    def like():

        try:
            data = request.json

            cursor.execute("""
                INSERT INTO "Like"
                ("userId","propertyId","createdAt")
                VALUES (%s,%s,NOW())
                ON CONFLICT DO NOTHING
            """, (
                data["userId"],
                data["propertyId"]
            ))

            return jsonify({"message": "liked"})

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # =========================
    # VISIT PROPERTY
    # =========================
    @app.route("/visit", methods=["POST"])
    def visit():

        try:
            data = request.json

            cursor.execute("""
                INSERT INTO "Visit"
                ("userId","propertyId","visitDateTime","status","createdAt")
                VALUES (%s,%s,%s,'pending',NOW())
            """, (
                data["userId"],
                data["propertyId"],
                data["visitDateTime"]
            ))

            return jsonify({"message": "visit booked"})

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # =========================
    # CHAT (AI)
    # =========================
    @app.route("/chat", methods=["POST"])
    def chat():

        try:
            msg = request.json["message"]

            res = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": msg}]
            )

            return jsonify({
                "reply": res.choices[0].message.content
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # =========================
    # RUN
    # =========================
    if __name__ == "__main__":
        app.run(debug=True)
