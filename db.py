import sqlite3
import os

DB_FILE = "wifi_manager.db"

def init_db():
    """初始化数据库并创建表"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS passwords (
            ssid TEXT PRIMARY KEY,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_all_passwords():
    """获取所有已保存的密码"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT ssid, password FROM passwords')
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def save_password(ssid, password):
    """保存或更新密码"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO passwords (ssid, password) VALUES (?, ?)', (ssid, password))
    conn.commit()
    conn.close()
