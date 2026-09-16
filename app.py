from flask import Flask, request, jsonify, render_template
import sqlite3
import random
import os

app = Flask(__name__)
DB_PATH = 'data/lottery.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs('data', exist_ok=True)
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS prizes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        total INTEGER NOT NULL,
        remaining INTEGER NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        has_drawn INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS winners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        prize_name TEXT NOT NULL,
        drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin')
def admin():
    return render_template('admin.html')


@app.route('/api/init', methods=['POST'])
def init_data():
    """管理员导入奖品和参与者名单"""
    data = request.json
    prizes = data.get('prizes', [])
    participants = data.get('participants', [])

    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM prizes")
    c.execute("DELETE FROM participants")
    c.execute("DELETE FROM winners")

    for p in prizes:
        c.execute("INSERT INTO prizes (name, total, remaining) VALUES (?, ?, ?)",
                  (p['name'], p['count'], p['count']))

    for name in participants:
        c.execute("INSERT OR IGNORE INTO participants (name) VALUES (?)", (name,))

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"已导入 {len(prizes)} 种奖品、{len(participants)} 位参与者"})


@app.route('/api/draw', methods=['POST'])
def draw():
    """用户抽奖接口"""
    data = request.json
    name = data.get('name', '').strip()

    if not name:
        return jsonify({"error": "请输入姓名"}), 400

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT has_drawn FROM participants WHERE name = ?", (name,))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({"error": "姓名不在参与名单中，请核对后重试"}), 400

    if row['has_drawn'] == 1:
        conn.close()
        return jsonify({"error": "您已经抽过奖了，每人只能抽一次"}), 400

    c.execute("SELECT SUM(remaining) FROM prizes")
    remaining_prizes = c.fetchone()[0] or 0

    c.execute("SELECT COUNT(*) FROM participants WHERE has_drawn = 0")
    remaining_people = c.fetchone()[0]

    if remaining_prizes <= 0:
        c.execute("UPDATE participants SET has_drawn = 1 WHERE name = ?", (name,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "prize": None, "message": "谢谢参与"})

    win_probability = remaining_prizes / remaining_people

    if random.random() < win_probability:
        c.execute("SELECT id, name, remaining FROM prizes WHERE remaining > 0")
        available = c.fetchall()
        weights = [row['remaining'] for row in available]
        chosen = random.choices(available, weights=weights, k=1)[0]

        c.execute("UPDATE prizes SET remaining = remaining - 1 WHERE id = ?", (chosen['id'],))
        c.execute("UPDATE participants SET has_drawn = 1 WHERE name = ?", (name,))
        c.execute("INSERT INTO winners (name, prize_name) VALUES (?, ?)",
                  (name, chosen['name']))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "prize": {"name": chosen['name']},
            "message": f"恭喜你抽中【{chosen['name']}】！"
        })
    else:
        c.execute("UPDATE participants SET has_drawn = 1 WHERE name = ?", (name,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "prize": None, "message": "谢谢参与"})


@app.route('/api/prizes', methods=['GET'])
def get_prizes():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, remaining FROM prizes ORDER BY id")
    prizes = [{"name": r['name'], "remaining": r['remaining']} for r in c.fetchall()]
    conn.close()
    return jsonify(prizes)


@app.route('/api/winners', methods=['GET'])
def get_winners():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, prize_name, drawn_at FROM winners ORDER BY drawn_at DESC")
    winners = [{"name": r['name'], "prize": r['prize_name'], "time": r['drawn_at']}
               for r in c.fetchall()]
    conn.close()
    return jsonify(winners)


@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM participants")
    total_people = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM participants WHERE has_drawn = 1")
    drawn_people = c.fetchone()[0]
    c.execute("SELECT SUM(remaining) FROM prizes")
    remaining_prizes = c.fetchone()[0] or 0
    c.execute("SELECT SUM(total) FROM prizes")
    total_prizes = c.fetchone()[0] or 0
    conn.close()
    return jsonify({
        "total_people": total_people,
        "drawn_people": drawn_people,
        "remaining_prizes": remaining_prizes,
        "total_prizes": total_prizes
    })


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)