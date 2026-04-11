import requests
from io import BytesIO
from PIL import Image
from supabase_client import supabase

BUCKET = "phones"

def process_image(phone):
    try:
        print("Processing:", phone["name"])

        if not phone.get("image_url"):
            print("No image URL, skipping")
            return

        # 1. Download image
        headers = {
            "User-Agent": "Mozilla/5.0",
        }

        response = requests.get(phone["image_url"], headers=headers, timeout=10)

        if response.status_code != 200:
            print("Using fallback image")

            response = requests.get(
                "https://via.placeholder.com/500x500?text=No+Image",
                timeout=10
            )

        # 2. Convert to WebP + resize
        img = Image.open(BytesIO(response.content)).convert("RGB")
        img.thumbnail((500, 500))  # resize (important)

        output = BytesIO()
        img.save(output, format="WEBP", quality=80)
        output.seek(0)

        file_name = f"{phone['id']}.webp"

        # 3. Upload to Supabase Storage
        supabase.storage.from_(BUCKET).upload(
            file_name,
            output.read(),
            {"content-type": "image/webp", "upsert": "true"}
        )

        # 4. Update DB
        supabase.table("phones").update({
            "image_url": file_name
        }).eq("id", phone["id"]).execute()

        print("✅ Done:", phone["name"])

    except Exception as e:
        print("❌ Error:", phone["name"], str(e))


def migrate_all():
    res = supabase.table("phones").select("*").execute()
    phones = res.data

    for phone in phones:
        process_image(phone)


if __name__ == "__main__":
    res = supabase.table("phones").select("*").execute()
    
    for phone in res.data:
        if not phone["image_url"].endswith(".webp"):
            process_image(phone)
