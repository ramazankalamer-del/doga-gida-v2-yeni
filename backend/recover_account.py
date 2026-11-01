"""Explicit local-only recovery server. Passwords are entered in the browser."""
import argparse
from pathlib import Path
import uvicorn
import main
import account_settings


def run():
    parser=argparse.ArgumentParser(description='Yerel yönetici hesabını kurtarır; normal sunucuyu önce kapatın.')
    parser.add_argument('user_id',type=int)
    parser.add_argument('--port',type=int,default=8015)
    parser.add_argument('--link-file',type=Path)
    args=parser.parse_args()
    main.initialize()
    token=account_settings.enable_recovery(main,args.user_id)
    link=f'http://127.0.0.1:{args.port}/#hesap-kurtarma={token}'
    if args.link_file:
        args.link_file.write_text(link,encoding='utf-8')
    else:
        print(link,flush=True)
    print('Kurtarma bağlantısı 15 dakika geçerlidir. Yeni bilgileri tarayıcıda kendiniz girin.',flush=True)
    uvicorn.run(main.app,host='127.0.0.1',port=args.port)


if __name__=='__main__':
    run()
