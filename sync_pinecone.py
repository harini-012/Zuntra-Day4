import os
import psycopg2
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

load_dotenv()

# =========================================
# CONNECT
# =========================================
print("Connecting to DB...")
conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
conn.autocommit = True
cursor = conn.cursor()

print("Connecting to Pinecone...")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX"))

print("Loading embedding model...")
embed_model = SentenceTransformer("BAAI/bge-large-en-v1.5")

# =========================================
# FETCH ALL PROPERTIES FROM DB
# =========================================
cursor.execute("""
    SELECT
        id,
        COALESCE("propertyName", 'Unnamed Property'),
        COALESCE(city, ''),
        COALESCE(locality, ''),
        COALESCE("propertyType", ''),
        COALESCE(street, ''),
        COALESCE(landmark, '')
    FROM "Property"
    ORDER BY id ASC
""")

rows = cursor.fetchall()
print(f"\nFound {len(rows)} properties in DB\n")

if not rows:
    print("No properties found in DB. Add some properties first.")
    exit()

# =========================================
# UPSERT INTO PINECONE
# =========================================
batch = []
success = 0
failed  = 0

for row in rows:
    try:
        pid       = row[0]
        prop_name = str(row[1])
        city      = str(row[2])
        locality  = str(row[3])
        prop_type = str(row[4])
        street    = str(row[5])
        landmark  = str(row[6])

        vector_text = (
            f"Property Name: {prop_name}\n"
            f"City: {city}\n"
            f"Locality: {locality}\n"
            f"Property Type: {prop_type}\n"
            f"Street: {street}\n"
            f"Landmark: {landmark}"
        )

        vector = embed_model.encode(vector_text).tolist()

        batch.append({
            "id": str(pid),
            "values": vector,
            "metadata": {
                "type":         "property",
                "propertyId":   pid,
                "propertyName": prop_name,
                "city":         city,
                "locality":     locality,
                "propertyType": prop_type
            }
        })

        print(f"  [{pid}] {prop_name} — {city}, {locality} ({prop_type})")

        # upsert in batches of 50
        if len(batch) >= 50:
            index.upsert(vectors=batch)
            success += len(batch)
            print(f"  >>> Upserted batch of {len(batch)}")
            batch = []

    except Exception as e:
        print(f"  ERROR on property {row[0]}: {e}")
        failed += 1

# upsert remaining
if batch:
    index.upsert(vectors=batch)
    success += len(batch)
    print(f"  >>> Upserted final batch of {len(batch)}")

# =========================================
# VERIFY
# =========================================
print(f"\n✅ Done! {success} properties synced, {failed} failed.")
print("\nVerifying Pinecone index stats...")
stats = index.describe_index_stats()
print(f"Total vectors in index: {stats.get('total_vector_count', stats)}")

# =========================================
# TEST SEARCH
# =========================================
print("\nTesting search for 'chennai properties'...")
test_vector = embed_model.encode("properties in chennai").tolist()
results = index.query(
    vector=test_vector,
    top_k=3,
    include_metadata=True,
    filter={"type": "property"}
)

matches = results.get("matches", [])
if matches:
    print(f"Search returned {len(matches)} results:")
    for m in matches:
        meta = m.get("metadata", {})
        print(f"  - {meta.get('propertyName')} | {meta.get('city')} | {meta.get('locality')} | score: {m.get('score', 0):.3f}")
else:
    print("No results returned — check your Pinecone index name and dimension settings.")

conn.close()
