import os
import json
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
import datetime
import pytz
import requests
import locale
import platform

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

# 環境変数から参加者の名前を取得
PARTICIPANTS_NAMES = os.getenv('PARTICIPANTS_NAMES', '').split(',')

# 日本語ロケールを設定
locale.setlocale(locale.LC_ALL, '')

# 日付をdatetimeオブジェクトに変換するフィルタを作成
@app.template_filter('todate')
def todate(date_str):
    return datetime.datetime.strptime(date_str, '%m/%d')

# 日付をdatetimeオブジェクトに変換し、その日付の曜日を日本語で取得するフィルタ
@app.template_filter('next_weekday')
def next_weekday(date_str):
    # 日付をdatetimeオブジェクトに変換
    date = datetime.datetime.strptime(date_str, '%m/%d')
    # 一日後の日付を取得
    next_day = date + datetime.timedelta(days=1)
    # 一日後の曜日を日本語で取得
    weekdays_jp = ['月', '火', '水', '木', '金', '土', '日']
    return weekdays_jp[next_day.weekday()]

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
        schedule = json.load(f)
    # OSに依存しない日付のフォーマット処理
    def parse_date(date_str):
        # 日付の文字列をdatetimeオブジェクトに変換
        return datetime.datetime.strptime(date_str, '%m/%d')
    # スケジュールを昇順にソート
    sorted_schedule = dict(sorted(schedule.items(), key=lambda item: parse_date(item[0])))
    return sorted_schedule

# スケジュールをJSONファイルに保存する
def save_schedule(schedule_dict):
    # 全ての予定が"plans"リストに格納されていることを確認して保存
    for date, details in schedule_dict.items():
        # detailsが辞書であり、'plans'キーが存在しない場合はplansを作成する
        if 'plans' not in details:
            # 既存のルートレベルの情報を"plans"リストに移動
            schedule_dict[date] = {
                "plans": [{
                    "plan_type": details.get('plan_type'),
                    "participants": details.get('participants', []),
                    "start_time": details.get('start_time'),
                    "end_time": details.get('end_time'),
                    "location": details.get('location'),
                    "last_updated": details.get('last_updated')
                }]
            }

    # JSONファイルに保存
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

# APIエンドポイント: スケジュールを取得する
@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    schedule = load_schedule()
    return jsonify(schedule)

@app.route('/api/update_schedule', methods=['POST'])
def update_schedule():
    global schedule_dict
    new_schedule = request.json  # 受け取ったJSONデータを取得
    if new_schedule:
        # 日付をdatetimeオブジェクトに変換して昇順にソート
        sorted_schedule = dict(sorted(new_schedule.items(), key=lambda item: datetime.datetime.strptime(item[0], '%m/%d')))
        schedule_dict = sorted_schedule  # グローバル変数を更新
        save_schedule(schedule_dict)  # 新しいスケジュールを保存
        print("スケジュールが更新されました。")
        return jsonify({"message": "スケジュールが更新されました。"}), 200
    else:
        return jsonify({"message": "スケジュールの更新に失敗しました。"}), 400


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
    return render_template('index.html', schedule=schedule_dict, participants_names=PARTICIPANTS_NAMES, user=current_user)

@app.route('/add', methods=['POST'])
@login_required
def add():
    if not current_user.is_admin:
        flash("管理者のみがスケジュールを追加できます。")
        return redirect(url_for('index'))

    date = request.form['date']  # 例: '2024-09-24'
    
    # OSによってフォーマットを変更
    if platform.system() == 'Windows':
        date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%#m/%#d')  # Windows用
    else:
        date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%-m/%-d')  # macOS/Linux用

    plan_type = request.form['plan_type']
    custom_plan_type = request.form.get('custom_plan_type')

    if plan_type == "その他" and custom_plan_type:
        plan_type = custom_plan_type

    participants = request.form.getlist('participants')
    start_time = request.form['start_time']
    end_time = request.form['end_time']
    location = request.form['location']
    custom_location = request.form.get('custom_location')

    if location == "その他" and custom_location:
        location = custom_location

    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')

    # 修正: 既存の予定に新しい予定を追加する際にplansリストを使用
    if date in schedule_dict:
        existing_plans = schedule_dict[date].get('plans', [])
        # 同じ種類の予定が既に存在するかをチェック
        if any(plan['plan_type'] == plan_type for plan in existing_plans):
            flash(f"追加しようとしている日は同じ予定がすでにあります: {date}")
            return redirect(url_for('index'))
        else:
            # 新しい予定をplansリストに追加
            existing_plans.append({
                "plan_type": plan_type,
                "participants": [p.strip() for p in participants],
                "start_time": start_time,
                "end_time": end_time,
                "location": location,
                "last_updated": now
            })
            schedule_dict[date]['plans'] = existing_plans
    else:
        # 新しい日付の場合は新しいplansリストを作成
        schedule_dict[date] = {
            "plans": [{
                "plan_type": plan_type,
                "participants": [p.strip() for p in participants],
                "start_time": start_time,
                "end_time": end_time,
                "location": location,
                "last_updated": now
            }]
        }

    # 日付でスケジュールをソートして保存
    def parse_date(date_str):
        return datetime.datetime.strptime(date_str, '%m/%d')

    sorted_schedule = dict(sorted(schedule_dict.items(), key=lambda item: parse_date(item[0])))

    schedule_dict.clear()
    schedule_dict.update(sorted_schedule)
    save_schedule(schedule_dict)

    if "全員" in schedule_dict[date]['plans'][0]['participants']:
        participants_str = '全員'
    else:
        participants_str = '・'.join(schedule_dict[date]['plans'][0]['participants']) + 'さん'

    message = f"新しい練習スケジュールが追加されました。\n予定: {plan_type}\n日付: {date}\n時間: {start_time} ～ {end_time}\n場所: {location}\n参加者: {participants_str}"
    #send_line_notify(message)

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

             # フォームから「予定」と「カスタム予定」を取得
            plan_type = request.form.get(f'plan_type_{date}')
            custom_plan_type = request.form.get(f'custom_plan_type_{date}')

            # 「予定」が「その他」の場合、自由入力された値を使用
            if plan_type == "その他" and custom_plan_type:
                plan_type = custom_plan_type
                
            # チェックボックスから選択された参加者を取得
            participants = request.form.getlist(f'participants_{date}')
            
            start_time = request.form.get(f'start_time_{date}')
            end_time = request.form.get(f'end_time_{date}')
            location = request.form.get(f'location_' + date)
            custom_location = request.form.get(f'custom_location_' + date)

            if location == "その他" and custom_location:
                location = custom_location

            # 現在の日本時間を取得して記録
            jst = pytz.timezone('Asia/Tokyo')
            now = datetime.datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')
            
            updated = {
                "plan_type": plan_type,  # 予定を更新
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
                # LINE Notifyの通知内容を設定
                if "全員" in schedule_dict[date]['participants']:
                    participants_str = '全員'
                else:
                    participants_str = '・'.join(schedule_dict[date]['participants']) + 'さん'
                # 新しいスケジュールの追加を通知
                message = f"練習スケジュールが更新されました。\n予定: {plan_type}\n日付: {date}\n時間: {start_time} ～ {end_time}\n場所: {location}\n参加者: {participants_str}"
                #send_line_notify(message)
        
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
            #send_line_notify(message)
        
            # 削除された件数をflashメッセージで表示
            flash(f"{len(deleted_dates)} 件のスケジュールが削除されました。")
        else:
            flash("選択された日付はスケジュールに存在しませんでした。")

        return redirect(url_for('index'))

@app.route('/filter', methods=['POST'])
@login_required
def filter():
    # "show_all"がフォームから送信された場合、全てのスケジュールを表示
    if 'show_all' in request.form:
        filtered_schedule = schedule_dict
    else:
        selected_participants = request.form.getlist('participants_filter')

        # 全員が選択されたかどうかを判定
        if set(selected_participants) == set(PARTICIPANTS_NAMES):
            # 全員が選ばれた場合、予定が「全体練習」のスケジュールを表示
            filtered_schedule = {
                date: details for date, details in schedule_dict.items()
                if any(plan['plan_type'] == "全体練習" for plan in details.get('plans', []))  # 予定が「全体練習」かを判定
            }
        else:
            # 一部の部員が選択された場合、選択された部員が参加しているか、全体練習が含まれるスケジュールを表示
            filtered_schedule = {
                date: details for date, details in schedule_dict.items()
                if any(all(participant in plan.get('participants', []) for participant in selected_participants) or plan['plan_type'] == "全体練習"
                       for plan in details.get('plans', []))
            }

    return render_template('index.html', schedule=filtered_schedule, participants_names=PARTICIPANTS_NAMES, user=current_user)



if __name__ == '__main__':
    app.run(debug=True)
