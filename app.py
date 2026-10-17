from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
CORS(app)

# --- DATABASE CONFIG ---
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "Snehaa18#",  # TODO: Change this to your MySQL password
    "database": "rentora_db"
}

def get_db_connection():
    """Helper to create a fresh connection for every request."""
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except Error as e:
        print(f"Database Connection Error: {e}")
        return None

# --- ROUTES ---

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "DB Connection Error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", 
                   (data['email'], data['password']))
    user = cursor.fetchone()
    
    cursor.close()
    conn.close()

    if user:
        return jsonify({
            "success": True, 
            "user_id": user['id'], 
            "name": f"{user['first_name']} {user['last_name']}", 
            "role": user['role'], 
            "points": user.get('reward_points', 0)
        })
    return jsonify({"success": False, "message": "Invalid credentials"})

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (first_name, last_name, email, phone, password, role) VALUES (%s, %s, %s, %s, %s, %s)",
            (data['first_name'], data['last_name'], data['email'], data['phone'], data['password'], data['role'])
        )
        conn.commit()
        return jsonify({"success": True})
    except Error as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route('/vehicles', methods=['GET'])
def get_vehicles():
    road_type = request.args.get('road_type')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if road_type:
        # Smart Suggestion Filter
        cursor.execute("SELECT * FROM vehicles WHERE road_type = %s AND status = 'Available'", (road_type,))
    else:
        cursor.execute("SELECT * FROM vehicles WHERE status = 'Available'")
    
    vehicles = cursor.fetchall()
    
    # Convert Decimal prices to float for JSON compatibility
    for v in vehicles:
        if 'price_per_day' in v:
            v['price_per_day'] = float(v['price_per_day'])

    cursor.close()
    conn.close()
    return jsonify(vehicles)

@app.route('/book', methods=['POST'])
def book():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Create the booking record
        cursor.execute(
            "INSERT INTO bookings (user_id, vehicle_id, start_date, end_date, status) VALUES (%s, %s, %s, %s, 'Active')",
            (data['user_id'], data['vehicle_id'], data['start_date'], data['end_date'])
        )
        # 2. Update vehicle to 'Rented'
        cursor.execute("UPDATE vehicles SET status = 'Rented' WHERE id = %s", (data['vehicle_id'],))
        
        conn.commit()
        return jsonify({"success": True, "message": "Booking confirmed!"})
    except Error as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        conn.close()
@app.route('/redeem', methods=['POST'])
def redeem_points():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Reset points to 0 after they are spent
        cursor.execute("UPDATE users SET reward_points = 0 WHERE id = %s", (data['user_id'],))
        conn.commit()
        return jsonify({"success": True, "message": "Points redeemed!"})
    except Error as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        conn.close()
@app.route('/cancel-booking/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Get the vehicle_id before updating the booking
        cursor.execute("SELECT vehicle_id FROM bookings WHERE id = %s", (booking_id,))
        res = cursor.fetchone()
        if not res:
            return jsonify({"success": False, "message": "Booking not found"}), 404
        
        vehicle_id = res[0]

        # 2. Update booking status to 'Cancelled'
        cursor.execute("UPDATE bookings SET status = 'Cancelled' WHERE id = %s", (booking_id,))
        
        # 3. Make the vehicle 'Available' again
        cursor.execute("UPDATE vehicles SET status = 'Available' WHERE id = %s", (vehicle_id,))
        
        conn.commit()
        return jsonify({"success": True, "message": "Booking cancelled successfully"})
    except Error as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        conn.close()
@app.route('/bookings/<int:user_id>', methods=['GET'])
def get_user_bookings(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT b.id, b.start_date, b.status, b.user_id, v.name as v_name, v.category, v.price_per_day 
        FROM bookings b JOIN vehicles v ON b.vehicle_id = v.id 
        WHERE b.user_id = %s
    """
    cursor.execute(query, (user_id,))
    rows = cursor.fetchall()
    
    result = [{
        "id": r['id'], 
        "start_date": str(r['start_date']), 
        "status": r['status'], 
        "user_id": r['user_id'],
        "vehicle": {
            "name": r['v_name'], 
            "category": r['category'], 
            "price_per_day": float(r['price_per_day']), 
            "status": "Rented"
        }
    } for r in rows]

    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/return', methods=['POST'])
def return_vehicle():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get user and vehicle details linked to this booking
        cursor.execute("SELECT user_id, vehicle_id FROM bookings WHERE id = %s", (data['booking_id'],))
        res = cursor.fetchone()
        
        if not res:
            return jsonify({"success": False, "message": "Booking not found"}), 404

        # Update everything in one transaction
        cursor.execute("UPDATE bookings SET status = 'Completed' WHERE id = %s", (data['booking_id'],))
        cursor.execute("UPDATE users SET reward_points = reward_points + %s WHERE id = %s", (data['reward_points'], res[0]))
        cursor.execute("UPDATE vehicles SET status = 'Available' WHERE id = %s", (res[1],))
        
        conn.commit()
        return jsonify({"success": True})
    except Error as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/bookings', methods=['GET'])
def admin_bookings():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT b.id, b.start_date, b.status, b.user_id, u.first_name, v.name as v_name, v.category, v.price_per_day
        FROM bookings b 
        JOIN users u ON b.user_id = u.id 
        JOIN vehicles v ON b.vehicle_id = v.id
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    
    result = [{
        "id": r['id'], 
        "start_date": str(r['start_date']), 
        "status": r['status'], 
        "user_id": r['user_id'], 
        "user_name": r['first_name'],
        "vehicle": {
            "name": r['v_name'], 
            "category": r['category'], 
            "price_per_day": float(r['price_per_day']), 
            "status": r['status']
        }
    } for r in rows]

    cursor.close()
    conn.close()
    return jsonify(result)

if __name__ == '__main__':
    # '0.0.0.0' allows external access from your Android/iOS device
    app.run(host='0.0.0.0', port=5000, debug=True)