"""Incomplete v1 storage; all helpers use a passed SQLite connection."""
import json
def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, target TEXT, before_version INTEGER, after_version INTEGER, request_key TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS receipts (actor TEXT, request_key TEXT, fingerprint TEXT, status INTEGER, body TEXT, PRIMARY KEY(actor,request_key))')
    db.commit()
def list_members(db):return [dict(zip(('id','email','name','role','status','version'),r)) for r in db.execute('SELECT id,email,name,role,status,version FROM members')]
def get_member(db,member_id):return next((r for r in list_members(db) if r['id']==member_id),None)
def put_member(db,row,create=False):
    db.execute('INSERT OR REPLACE INTO members(id,email,name,role,status,version) VALUES(:id,:email,:name,:role,:status,:version)',row)
    db.commit()
def get_receipt(db,actor,key):return None
def put_receipt(db,actor,key,fingerprint,status,body):pass
def append_audit(db,actor,action,target,before_version,after_version,key):pass
def list_audit(db):return []
