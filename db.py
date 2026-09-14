import sqlite3,json
from datetime import datetime
from config import DB_PATH

def init():
 c=sqlite3.connect(DB_PATH); c.executescript('''CREATE TABLE IF NOT EXISTS snapshots(ts TEXT,price REAL,ath REAL,drawdown REAL,score INTEGER,regime TEXT,decision TEXT,payload TEXT); CREATE TABLE IF NOT EXISTS alerts(ts TEXT,kind TEXT,message TEXT);'''); c.commit(); c.close()
def save_snapshot(row):
 c=sqlite3.connect(DB_PATH); c.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?,?,?)',row); c.commit(); c.close()
def save_alert(kind,msg):
 c=sqlite3.connect(DB_PATH); c.execute('INSERT INTO alerts VALUES(?,?,?)',(datetime.utcnow().isoformat(),kind,msg)); c.commit(); c.close()
def history(n=50):
 c=sqlite3.connect(DB_PATH); x=c.execute('SELECT ts,price,drawdown,score,regime,decision FROM snapshots ORDER BY ts DESC LIMIT ?', (n,)).fetchall(); c.close(); return x
def alerts(n=20):
 c=sqlite3.connect(DB_PATH); x=c.execute('SELECT ts,kind,message FROM alerts ORDER BY ts DESC LIMIT ?', (n,)).fetchall(); c.close(); return x
