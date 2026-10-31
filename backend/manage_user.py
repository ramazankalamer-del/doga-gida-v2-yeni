"""Local operator command. Passwords are read invisibly, never from arguments."""
import argparse
import getpass
import auth
import main

def create_user(username, password, role):
    username = username.strip().lower()
    if not username or len(username) > 100:
        raise ValueError('Kullanıcı adı 1–100 karakter olmalı.')
    if not 12 <= len(password) <= 128:
        raise ValueError('Parola 12–128 karakter olmalı.')
    if role not in ('admin', 'staff', 'viewer'):
        raise ValueError('Geçersiz rol.')
    main.initialize()
    with main.database() as db:
        db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)', (username,auth.password_hash(password),role))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Yerel kullanıcı oluştur')
    parser.add_argument('username')
    parser.add_argument('--role', choices=['admin','staff','viewer'], required=True)
    args = parser.parse_args()
    password = getpass.getpass('Parola (en az 12 karakter): ')
    if password != getpass.getpass('Parola tekrar: '):
        parser.error('Parolalar eşleşmiyor.')
    create_user(args.username, password, args.role)
    print('Kullanıcı oluşturuldu.')
