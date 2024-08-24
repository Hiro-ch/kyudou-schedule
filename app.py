import os
import json
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
import datetime
import pytz
import requests
import locale
import schedule
import time
import threading
import platform
from datetime import timedelta

# .envファイルから環境変数をロード
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_default_secret_key')

@app.route('/static/<path:filename>')
def custom_static(filename):
    # send_from_directoryを使用して静的ファイルを配信
    # cache_timeoutを秒単位で指定（ここでは1時間=3600秒）
    return send_from_directory('static', filename, cache_timeout=3600)

# Flask-Loginの設定
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # ログインページを指定

# セッションが永続化されないように設定
app.config['SESSION_PERMANENT'] = False

# 一般ユーザーのパスワードを環境変数から取得
USER_PASSWORD = os.getenv('USER_PASSWORD')

# 管理者情報を環境変数から取得
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

# 日本語ロケールを設定
locale.setlocale(locale.LC_ALL, '')

# 日付をdatetimeオブジェクトに変換するフィルタを作成
@app.template_filter('todate')
def todate(date_str):
    return datetime.datetime.strptime(date_str, '%m/%d')

# 日付をdatetimeオブジェクトに変換し、その日付の曜日を取得するフィルタ
@app.template_filter('next_weekday')
def next_weekday(date_str):
    # 日付をdatetimeオブジェクトに変換
    date = datetime.datetime.strptime(date_str, '%m/%d')
    # 一日後の日付を取得
    next_day = date + datetime.timedelta(days=1)
    # 一日後の曜日を取得
    return next_day.strftime('%A')


# ダミーユーザークラス
class User(UserMixin):
    def __init__(self, id, is_admin=False):
        self.id = id
        self.is_admin = is_admin

# ユーザーのロード方法
@login_manager.user_loader
def load_user(user_id):
    if user_id == "1":
        return User(id=1, is_admin=True)  # 管理者ユーザー
    elif user_id == "2":
        return User(id=2, is_admin=False)  # 一般ユーザー
    return None

# 共通のログインページのルート
@app.route('/login')
def login():
    return render_template('login.html')

# スケジュールをJSONファイルから読み込む
def load_schedule():
    with open('schedule.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# スケジュールをJSONファイルに保存する
def save_schedule(schedule_dict):
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(schedule_dict, f, ensure_ascii=False, indent=4)

# 練習スケジュールを読み込み
schedule_dict = load_schedule()

# LINE Notifyの設定
line_notify_token = os.getenv('LINE_NOTIFY_TOKEN')
line_notify_api = 'https://notify-api.line.me/api/notify'

def send_line_notify(message):
    headers = {
        'Authorization': f'Bearer {line_notify_token}'
    }
    data = {
        'message': message
    }
    response = requests.post(line_notify_api, headers=headers, data=data)
    if response.status_code == 200:
        print("LINE通知を送信しました。")
    else:
        print(f"通知の送信に失敗しました: {response.status_code}")

def notify_tomorrow_schedule():
    # 日本時間を設定
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.datetime.now(jst)
    
    # 翌日の日付を取得
    tomorrow = now + datetime.timedelta(days=1)
    
    # OSによってフォーマットを変更
    if platform.system() == 'Windows':
        tomorrow_str = tomorrow.strftime('%#m/%#d')  # Windows用
    else:
        tomorrow_str = tomorrow.strftime('%-m/%-d')  # macOS/Linux用
    
    # 翌日の練習スケジュールを取得
    if tomorrow_str in schedule_dict:
        details = schedule_dict[tomorrow_str]
        start_time = details['start_time']
        end_time = details['end_time']
        location = details['location']
        participants = ', '.join(details['participants'])
        
        message = (
            f"\n明日 ({tomorrow_str}) の練習予定です。\n"
            f"時間: {start_time}～{end_time}\n"
            f"場所: {location}\n"
            f"参加者: {participants}さん\n"
            "明日も頑張りましょう！"
        )
        send_line_notify(message)
    else:
        send_line_notify(f"\n明日 ({tomorrow_str}) は練習の予定はありません。")

# 一般ユーザー用ログインページのルート
@app.route('/user_login', methods=['POST'])
def user_login():
    password = request.form['user_password']

    # 一般ユーザーのパスワードをチェック
    if password == USER_PASSWORD:
        user = User(id=2, is_admin=False)
        login_user(user, remember=False)
        return redirect(url_for('index'))
    else:
        flash('ログインに失敗しました。パスワードが間違っています。')
        return redirect(url_for('login'))

# 管理者用ログインページのルート
@app.route('/admin_login', methods=['POST'])
def admin_login():
    username = request.form['username']
    password = request.form['password']

    # 管理者のユーザー名とパスワードをチェック
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        user = User(id=1, is_admin=True)
        login_user(user, remember=False)
        return redirect(url_for('index'))
    else:
        flash('ログインに失敗しました。ユーザー名またはパスワードが間違っています。')
        return redirect(url_for('login'))

# ログアウトのルート
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# メインページ（ログインが必要）
@app.route('/')
@login_required
def index():
    return render_template('index.html', schedule=schedule_dict, user=current_user)

@app.route('/add', methods=['POST'])
@login_required
def add():
    if not current_user.is_admin:
        flash("管理者のみがスケジュールを追加できます。")
        return redirect(url_for('index'))

    # YYYY-MM-DD 形式の日付を取得
    date = request.form['date']  # 例: '2024-09-24'
    
    # OSによってフォーマットを変更
    if platform.system() == 'Windows':
        date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%#m/%#d')  # Windows用
    else:
        date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%-m/%-d')  # macOS/Linux用

    participants = request.form['participants'].split(',')
    start_time = request.form['start_time']
    end_time = request.form['end_time']
    location = request.form['location']
    custom_location = request.form.get('custom_location')

    # 「その他」が選択され、自由入力フィールドが記入されている場合、その内容を保存
    if location == "その他" and custom_location:
        location = custom_location

    # 現在の日時を取得して記録
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    schedule_dict[date] = {
        "participants": [p.strip() for p in participants],
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "last_updated": now
    }

    # スケジュールを保存
    save_schedule(schedule_dict)

    # 新しいスケジュールの追加を通知
    message = f"新しい練習スケジュールが追加されました。\n日付: {date}\n時間: {start_time} - {end_time}\n場所: {location}\n参加者: {'・'.join(schedule_dict[date]['participants'])}さん"
    send_line_notify(message)

    flash("新しいスケジュールが追加されました。")
    return redirect(url_for('index'))

@app.route('/manage', methods=['POST'])
@login_required
def manage():
    if not current_user.is_admin:
        flash("管理者のみが編集できます。")
        return redirect(url_for('index'))

    action = request.form.get('action')
    selected_dates = request.form.getlist('dates')
    
    if action == 'edit':
        changes_made = False
        updated_dates = []

        for date in selected_dates:
            original = schedule_dict.get(date, {})
            participants = request.form.get(f'participants_{date}').split(',')
            start_time = request.form.get(f'start_time_{date}')
            end_time = request.form.get(f'end_time_{date}')
            location = request.form.get(f'location_' + date)
            custom_location = request.form.get(f'custom_location_' + date)

            if location == "その他" and custom_location:
                location = custom_location

            # 現在の日時を取得して記録
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            updated = {
                "participants": [p.strip() for p in participants],
                "start_time": start_time,
                "end_time": end_time,
                "location": location,
                "last_updated": now
            }

            if original != updated:
                schedule_dict[date] = updated
                updated_dates.append(date)
                changes_made = True

        if changes_made:
            # スケジュールを保存
            save_schedule(schedule_dict)

            # 各編集された練習情報を通知
            for date in updated_dates:
                message = f"練習スケジュールが更新されました。\n日付: {date}\n時間: {schedule_dict[date]['start_time']} - {schedule_dict[date]['end_time']}\n場所: {schedule_dict[date]['location']}\n参加者: {'・'.join(schedule_dict[date]['participants'])}さん"
                send_line_notify(message)
        
            flash(f"{len(updated_dates)} 件の変更が保存されました。")
        else:
            flash("変更がありません。")

        return redirect(url_for('index'))

    elif action == 'delete':
        if not selected_dates:
            flash("削除する日付を選択してください。")
            return redirect(url_for('index'))

        deleted_dates = []

        for date in selected_dates:
            if date in schedule_dict:
                del schedule_dict[date]
                deleted_dates.append(date)

        if deleted_dates:
            # スケジュールを保存
            save_schedule(schedule_dict)

            # 削除された情報を通知
            message = f"練習スケジュールが削除されました。\n日付: {', '.join(deleted_dates)}"
            send_line_notify(message)
        
            # 削除された件数をflashメッセージで表示
            flash(f"{len(deleted_dates)} 件のスケジュールが削除されました。")
        else:
            flash("選択された日付はスケジュールに存在しませんでした。")

        return redirect(url_for('index'))

        
def run_scheduler():
    schedule.clear()

    # シンガポール時間のオフセットを日本時間に合わせる
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.datetime.now(pytz.timezone('Asia/Singapore'))
    jst_time = now.astimezone(jst)

    # JSTの20:00に対応するシンガポール時間を計算
    target_time = jst_time.replace(hour=20, minute=0, second=0, microsecond=0)
    if target_time < now:
        target_time += datetime.timedelta(days=1)

    # シンガポール時間に合わせてスケジュールを設定
    schedule_time = target_time.strftime('%H:%M:%S')
    schedule.every().day.at(schedule_time).do(notify_tomorrow_schedule)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    # スケジュールジョブをバックグラウンドで実行
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    app.run(debug=True)
