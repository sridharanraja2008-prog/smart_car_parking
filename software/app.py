from flask import Flask, render_template, jsonify, request
import serial
import threading
from datetime import datetime
from pymongo import MongoClient, DESCENDING
import os

app = Flask(__name__)

# ==========================
# ARDUINO SETTINGS
# ==========================

arduino_port = "COM7"
baud_rate = 9600


# ==========================
# BILLING SETTINGS
# ==========================

RATE_PER_HOUR = 20        # currency units charged per hour
MIN_CHARGE = RATE_PER_HOUR  # minimum charge per visit (1 hour). Set to 0 to disable.
CURRENCY_SYMBOL = "₹"


# ==========================
# MONGODB SETTINGS
# ==========================
# Change MONGO_URI if using MongoDB Atlas, e.g.:
# "mongodb+srv://<user>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority"

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017"
)
DB_NAME = "smart_parking"

mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo_client[DB_NAME]
history_collection = db["parking_history"]

# Explicit connectivity check — MongoClient() alone does NOT fail even if
# the server is unreachable, since pymongo connects lazily. This forces
# a real round-trip so you get a clear yes/no at startup.
try:
    mongo_client.admin.command("ping")
    print(f"[MongoDB] Connected successfully -> {MONGO_URI} (db: {DB_NAME})")
except Exception as error:
    print(f"[MongoDB] Connection FAILED -> {MONGO_URI}")
    print(f"[MongoDB] Error: {error}")
    print("[MongoDB] The app will still start, but history/monthly-stats "
          "routes will fail until MongoDB is reachable.")

# Helpful indexes for fast filtering
history_collection.create_index([("date", DESCENDING)])
history_collection.create_index([("slot", 1)])
history_collection.create_index([("cost", 1)])
history_collection.create_index([("entry_dt", DESCENDING)])
history_collection.create_index([("month", 1)])


# ==========================
# PARKING DATA (live, in-memory)
# ==========================

parking_data = {
    "slot1": "EMPTY",
    "slot2": "EMPTY"
}

entry_times = {
    "slot1": None,
    "slot2": None
}


# ==========================
# HELPERS
# ==========================

def calculate_cost(duration):
    """Calculate parking cost from a timedelta duration."""
    hours = duration.total_seconds() / 3600
    cost = round(hours * RATE_PER_HOUR, 2)
    if MIN_CHARGE:
        cost = max(cost, MIN_CHARGE)
    return round(cost, 2)


def format_duration(total_seconds):
    """Format seconds as 'HHh MMm SSs' for readable display."""
    total_seconds = int(max(total_seconds, 0))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}h {m:02d}m {s:02d}s"


def save_history_entry(slot_label, entry_time, exit_time, duration, cost):
    """Persist a completed parking session to MongoDB."""

    doc = {
        "slot": slot_label,

        "date": entry_time.strftime("%Y-%m-%d"),
        "month": entry_time.strftime("%Y-%m"),

        "entry_time": entry_time.strftime("%I:%M:%S %p"),
        "exit_time": exit_time.strftime("%I:%M:%S %p"),

        # Full datetimes kept for accurate range/time filtering
        "entry_dt": entry_time,
        "exit_dt": exit_time,

        "duration": str(duration).split(".")[0],
        "duration_seconds": duration.total_seconds(),

        "cost": cost
    }

    history_collection.insert_one(doc)
    return doc


def serialize_doc(doc):
    """Convert a MongoDB document into JSON-safe output."""

    return {
        "slot": doc["slot"],
        "date": doc["date"],
        "entry_time": doc["entry_time"],
        "exit_time": doc["exit_time"],
        "duration": doc["duration"],
        "duration_seconds": doc["duration_seconds"],
        "cost": doc["cost"]
    }


# ==========================
# ARDUINO READING FUNCTION
# ==========================

def read_arduino():

    global parking_data

    try:

        arduino = serial.Serial(
            arduino_port,
            baud_rate,
            timeout=1
        )

        print("Arduino Connected!")

        while True:

            data = arduino.readline().decode(
                "utf-8",
                errors="ignore"
            ).strip()

            if data:

                print("Received:", data)

                if data.startswith("SLOT1:"):

                    try:

                        parts = data.split(",")

                        new_slot1 = parts[0].split(":")[1].strip()
                        new_slot2 = parts[1].split(":")[1].strip()


                        # ==========================
                        # CHECK SLOT 1
                        # ==========================

                        old_slot1 = parking_data["slot1"]

                        if old_slot1 == "EMPTY" and new_slot1 == "OCCUPIED":

                            entry_times["slot1"] = datetime.now()

                            print(
                                "Slot 1 Vehicle Entered:",
                                entry_times["slot1"]
                            )


                        elif old_slot1 == "OCCUPIED" and new_slot1 == "EMPTY":

                            exit_time = datetime.now()

                            entry_time = entry_times["slot1"]

                            if entry_time:

                                duration = exit_time - entry_time
                                cost = calculate_cost(duration)

                                save_history_entry(
                                    "Slot 1",
                                    entry_time,
                                    exit_time,
                                    duration,
                                    cost
                                )

                                print(
                                    "Slot 1 Vehicle Exited | Cost:",
                                    f"{CURRENCY_SYMBOL}{cost}"
                                )

                            entry_times["slot1"] = None


                        # ==========================
                        # CHECK SLOT 2
                        # ==========================

                        old_slot2 = parking_data["slot2"]

                        if old_slot2 == "EMPTY" and new_slot2 == "OCCUPIED":

                            entry_times["slot2"] = datetime.now()

                            print(
                                "Slot 2 Vehicle Entered:",
                                entry_times["slot2"]
                            )


                        elif old_slot2 == "OCCUPIED" and new_slot2 == "EMPTY":

                            exit_time = datetime.now()

                            entry_time = entry_times["slot2"]

                            if entry_time:

                                duration = exit_time - entry_time
                                cost = calculate_cost(duration)

                                save_history_entry(
                                    "Slot 2",
                                    entry_time,
                                    exit_time,
                                    duration,
                                    cost
                                )

                                print(
                                    "Slot 2 Vehicle Exited | Cost:",
                                    f"{CURRENCY_SYMBOL}{cost}"
                                )

                            entry_times["slot2"] = None


                        # UPDATE CURRENT STATUS

                        parking_data["slot1"] = new_slot1
                        parking_data["slot2"] = new_slot2

                        print("Updated Website Data:", parking_data)


                    except Exception as error:

                        print("Data Processing Error:", error)


    except Exception as error:

        print("Arduino Error:", error)


# ==========================
# DATABASE STATUS CHECK
# ==========================

@app.route("/db-status")
def get_db_status():

    try:
        mongo_client.admin.command("ping")
        record_count = history_collection.count_documents({})

        return jsonify({
            "connected": True,
            "database": DB_NAME,
            "records_stored": record_count
        })

    except Exception as error:
        return jsonify({
            "connected": False,
            "error": str(error)
        }), 500


# ==========================
# WEBSITE
# ==========================

@app.route("/")
def home():

    return render_template("index.html")


# ==========================
# LIVE PARKING DATA (unchanged real-time source)
# ==========================

@app.route("/parking-data")
def get_parking_data():

    now = datetime.now()

    result = {

        "slot1": parking_data["slot1"],
        "slot2": parking_data["slot2"],

        "entry_time_slot1": "",
        "entry_time_slot2": "",

        "duration_slot1": "",
        "duration_slot2": "",

        "cost_slot1": 0,
        "cost_slot2": 0,

        "currency": CURRENCY_SYMBOL

    }

    for slot in ["slot1", "slot2"]:

        if entry_times[slot]:

            result[f"entry_time_{slot}"] = entry_times[slot].strftime(
                "%I:%M:%S %p"
            )

            elapsed = now - entry_times[slot]

            result[f"duration_{slot}"] = format_duration(
                elapsed.total_seconds()
            )

            result[f"cost_{slot}"] = calculate_cost(elapsed)

    return jsonify(result)


# ==========================
# PARKING HISTORY (with filters: date, time range, cost range, slot)
# ==========================

@app.route("/parking-history")
def get_parking_history():

    query = {}

    # ---- Date filters ----
    # ?date=2026-09-02  -> single day
    # ?start_date=2026-09-01&end_date=2026-09-07 -> date range
    date_param = request.args.get("date")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if date_param:
        query["date"] = date_param

    elif start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = start_date
        if end_date:
            date_filter["$lte"] = end_date
        query["date"] = date_filter

    # ---- Time-of-day filter ----
    # ?start_time=09:00&end_time=18:00  (24-hour "HH:MM", filters by entry time of day)
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    if start_time or end_time:

        time_conditions = []

        if start_time:
            sh, sm = map(int, start_time.split(":"))
            time_conditions.append({
                "$gte": [
                    {"$add": [
                        {"$multiply": [{"$hour": "$entry_dt"}, 60]},
                        {"$minute": "$entry_dt"}
                    ]},
                    sh * 60 + sm
                ]
            })

        if end_time:
            eh, em = map(int, end_time.split(":"))
            time_conditions.append({
                "$lte": [
                    {"$add": [
                        {"$multiply": [{"$hour": "$entry_dt"}, 60]},
                        {"$minute": "$entry_dt"}
                    ]},
                    eh * 60 + em
                ]
            })

        query["$expr"] = {"$and": time_conditions} if len(time_conditions) > 1 else time_conditions[0]

    # ---- Cost filters ----
    # ?min_cost=10&max_cost=100
    min_cost = request.args.get("min_cost")
    max_cost = request.args.get("max_cost")

    if min_cost or max_cost:
        cost_filter = {}
        if min_cost:
            cost_filter["$gte"] = float(min_cost)
        if max_cost:
            cost_filter["$lte"] = float(max_cost)
        query["cost"] = cost_filter

    # ---- Slot filter ----
    # ?slot=Slot 1
    slot_param = request.args.get("slot")
    if slot_param:
        query["slot"] = slot_param

    # ---- Limit ----
    limit = int(request.args.get("limit", 100))

    cursor = history_collection.find(query).sort("entry_dt", DESCENDING).limit(limit)

    results = [serialize_doc(doc) for doc in cursor]

    return jsonify(results)


# ==========================
# DAILY OCCUPIED / FREE TIME + REVENUE
# ==========================

@app.route("/daily-stats")
def get_daily_stats():

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    midnight = datetime.combine(now.date(), datetime.min.time())
    seconds_since_midnight = (now - midnight).total_seconds()

    stats = {}
    total_revenue_today = 0.0

    today_docs = list(history_collection.find({"date": today_str}))

    for slot_key, slot_label in [("slot1", "Slot 1"), ("slot2", "Slot 2")]:

        slot_docs = [d for d in today_docs if d["slot"] == slot_label]

        occupied_seconds = sum(d["duration_seconds"] for d in slot_docs)
        revenue_today = sum(d["cost"] for d in slot_docs)

        active_entry = entry_times[slot_key]

        if active_entry and active_entry.strftime("%Y-%m-%d") == today_str:

            live_elapsed = now - active_entry

            occupied_seconds += live_elapsed.total_seconds()
            revenue_today += calculate_cost(live_elapsed)

        free_seconds = max(0, seconds_since_midnight - occupied_seconds)

        total_revenue_today += revenue_today

        stats[slot_key] = {

            "occupied_seconds": int(occupied_seconds),
            "free_seconds": int(free_seconds),

            "occupied_formatted": format_duration(occupied_seconds),
            "free_formatted": format_duration(free_seconds),

            "occupied_percent": round(
                (occupied_seconds / seconds_since_midnight) * 100, 1
            ) if seconds_since_midnight > 0 else 0,

            "revenue_today": round(revenue_today, 2)

        }

    stats["total_revenue_today"] = round(total_revenue_today, 2)
    stats["currency"] = CURRENCY_SYMBOL

    return jsonify(stats)


# ==========================
# MONTHLY INCOME + VEHICLES PARKED
# ==========================

@app.route("/monthly-stats")
def get_monthly_stats():

    # ?month=2026-09  (defaults to current month)
    month_param = request.args.get("month", datetime.now().strftime("%Y-%m"))

    docs = list(history_collection.find({"month": month_param}))

    total_revenue = round(sum(d["cost"] for d in docs), 2)
    total_vehicles = len(docs)

    slot_breakdown = {}
    for slot_label in ["Slot 1", "Slot 2"]:
        slot_docs = [d for d in docs if d["slot"] == slot_label]
        slot_breakdown[slot_label] = {
            "vehicles": len(slot_docs),
            "revenue": round(sum(d["cost"] for d in slot_docs), 2),
            "total_parked_seconds": sum(d["duration_seconds"] for d in slot_docs)
        }

    # Per-day breakdown within the month, for a simple chart on the frontend
    daily_breakdown = {}
    for d in docs:
        day = d["date"]
        if day not in daily_breakdown:
            daily_breakdown[day] = {"vehicles": 0, "revenue": 0}
        daily_breakdown[day]["vehicles"] += 1
        daily_breakdown[day]["revenue"] = round(
            daily_breakdown[day]["revenue"] + d["cost"], 2
        )

    return jsonify({
        "month": month_param,
        "total_revenue": total_revenue,
        "total_vehicles": total_vehicles,
        "slot_breakdown": slot_breakdown,
        "daily_breakdown": daily_breakdown,
        "currency": CURRENCY_SYMBOL
    })


# ==========================
# AVAILABLE MONTHS (for a month picker on the frontend)
# ==========================

@app.route("/available-months")
def get_available_months():

    months = history_collection.distinct("month")
    months.sort(reverse=True)

    return jsonify(months)


# ==========================
# START SERVER
# ==========================

if __name__ == "__main__":

    thread = threading.Thread(
        target=read_arduino,
        daemon=True
    )

    thread.start()


    app.run(
        debug=True,
        use_reloader=False
    )