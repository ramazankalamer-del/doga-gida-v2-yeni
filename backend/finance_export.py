from decimal import Decimal
from html import escape
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

def clean(value):
    return ''.join(c for c in str(value) if c in '\n\r\t' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)

def money(cents):
    return Decimal(cents) / 100

def tables(data, start=None, end=None):
    scope = next((a['name'] for a in data['accounts'] if a['id'] == data.get('selected_account_id')), 'Tüm hesaplar')
    summary = [['Hesap filtresi', scope], ['Başlangıç', str(start) if start else 'İlk kayıttan'], ['Bitiş', str(end) if end else 'Son kayda kadar']]
    for label, key in [('Giriş', 'income_cents'), ('Gider', 'expense_cents'), ('Diğer çıkış', 'withdrawal_cents'), ('Aktarım girişi', 'transfer_in_cents'), ('Aktarım çıkışı', 'transfer_out_cents')]:
        summary.append([label + ' (TL)', money(data[key])])
    summary.append(['Not', 'Güncel bakiyeler tarih filtresinden bağımsızdır; iptaller dönem toplamına dahil değildir.'])
    accounts = [['Hesap', 'Tür', 'Açılış (TL)', 'Güncel bakiye (TL)']] + [[a['name'], 'Kasa' if a['kind'] == 'cash' else 'Banka', money(a['opening_cents']), money(a['balance_cents'])] for a in data['accounts']]
    categories = [['Kategori', 'Kayıt', 'Toplam (TL)']] + [[r['category'], r['count'], money(r['amount_cents'])] for r in data['expense_categories']]
    rows = [['Tarih', 'Hesap', 'Tür', 'Tutar (TL)', 'Kategori', 'Açıklama', 'Kullanıcı', 'Durum', 'İptal nedeni']]
    for e in data['entries']:
        kind = {'income': 'Para girişi', 'withdrawal': 'Diğer çıkış', 'expense': 'Gider'}[e['kind']]
        if e['transfer_id']:
            kind = 'Aktarım #' + str(e['transfer_id']) + (' giriş' if e['kind'] == 'income' else ' çıkış')
        elif e['collection_id']:
            kind = 'Tahsilat TH-' + str(e['collection_id'])
        elif e.get('supplier_payment_id'):
            kind = 'Tedarikçi ödemesi #' + str(e['supplier_payment_id'])
        rows.append([e['date'], e['account_name'], kind, money(e['amount_cents']), e['category'], e['note'], e['username'], 'İptal edildi' if e['cancellation'] else 'Geçerli', e['cancellation']['reason'] if e['cancellation'] else ''])
    return [('Dönem Özeti', summary), ('Hesaplar', accounts), ('Gider Kategorileri', categories), ('Hareketler', rows)]

def xlsx(data, start=None, end=None):
    sheets = tables(data, start, end)
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as z:
        overrides = ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets) + 1))
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + overrides + '</Types>')
        z.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>' + ''.join(f'<sheet name="{escape(name, quote=True)}" sheetId="{i}" r:id="rId{i}"/>' for i, (name, _) in enumerate(sheets, 1)) + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + f'<Relationship Id="rId{len(sheets)+1}" Type="{REL}/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/styles.xml', f'<styleSheet xmlns="{NS}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for index, (_, rows) in enumerate(sheets, 1):
            chunks = []
            for number, row in enumerate(rows, 1):
                cells = []
                for column, value in enumerate(row, 1):
                    letters, n = '', column
                    while n:
                        n, mod = divmod(n - 1, 26)
                        letters = chr(65 + mod) + letters
                    ref = f'{letters}{number}'
                    if isinstance(value, (int, Decimal)):
                        cells.append(f'<c r="{ref}" s="{1 if isinstance(value, Decimal) else 0}"><v>{value}</v></c>')
                    else:
                        cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(clean(value))}</t></is></c>')
                chunks.append(f'<row r="{number}">' + ''.join(cells) + '</row>')
            z.writestr(f'xl/worksheets/sheet{index}.xml', f'<worksheet xmlns="{NS}"><cols><col min="1" max="9" width="24" customWidth="1"/></cols><sheetData>' + ''.join(chunks) + '</sheetData></worksheet>')
    return output.getvalue()

def printable(data, start=None, end=None, generated=''):
    parts = []
    for name, rows in tables(data, start, end):
        parts.append('<h2>' + escape(name) + '</h2><table>')
        for index, row in enumerate(rows):
            tag = 'th' if index == 0 and name != 'Dönem Özeti' else 'td'
            parts.append('<tr>' + ''.join(f'<{tag}>' + escape(format(value,',.2f').replace(',', '_').replace('.', ',').replace('_', '.') if isinstance(value, Decimal) else str(value)) + f'</{tag}>' for value in row) + '</tr>')
        parts.append('</table>')
    return '<!doctype html><html lang="tr"><meta charset="utf-8"><title>Doğa Gıda Finans Çıktısı</title><style>body{font:12px Arial;margin:24px}table{width:100%;border-collapse:collapse;margin:12px 0 24px}td,th{border:1px solid #ccc;padding:7px;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere}th{background:#edf4ed}tr{break-inside:avoid}@page{size:A4 landscape;margin:12mm}@media print{button{display:none}}</style><h1>Doğa Gıda — Finans Çıktısı</h1><p>Hazırlama tarihi: ' + escape(generated) + '</p><button onclick="window.print()">Yazdır / PDF olarak kaydet</button>' + ''.join(parts) + '</html>'
