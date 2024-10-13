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
import uuid  # ユニークIDを生成するために追加
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# .envファイルから環境変数をロード
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_default_secret_key')

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory('static', filename, cache_timeout=3600)

# Flask-Loginの設定
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.config['SESSION_PERMANENT'] = False

# 環境変数から情報を取得
USER_PASSWORD = os.getenv('USER_PASSWORD')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
PARTICIPANTS_NAMES = os.getenv('PARTICIPANTS_NAMES', '').split(',')
# .envファイルからLINEのチャネルシークレットとアクセストークンを取得
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

locale.setlocale(locale.LC_ALL, '')

# 日付をdatetimeオブジェクトに変換するフィルタを作成
@app.template_filter('todate')
def todate(date_str):
    return datetime.datetime.strptime(date_str, '%m/%d')

# 日付をdatetimeオブジェクトに変換し、その日付の曜日を日本語で取得するフィルタ
@app.template_filter('next_weekday')
def next_weekday(date_str):
    # date_strを月と日に分割
    month, day = map(int, date_str.split('/'))
    # 今日の日付を取得
    today = datetime.date.today()
    # 現在の年を取得
    current_year = today.year
    # 日付オブジェクトを作成
    try:
        date = datetime.date(current_year, month, day)
    except ValueError:
        # 例えば2月29日など、存在しない日付の場合は翌年に設定
        date = datetime.date(current_year + 1, month, day)
    # 日付が今日より前の場合は翌年に設定
    if date < today:
        date = date.replace(year=current_year + 1)
    # 曜日リスト（0:月曜日, 6:日曜日）
    weekdays_jp = ['月', '火', '水', '木', '金', '土', '日']
    return weekdays_jp[date.weekday()]

# ダミーユーザークラス
class User(UserMixin):
    def __init__(self, id, is_admin=False):
        self.id = id
        self.is_admin = is_admin

# ユーザーのロード方法
@login_manager.user_loader
def load_user(user_id):
    if user_id == "1":
        return User(id=1, is_admin=True)
    elif user_id == "2":
        return User(id=2, is_admin=False)
    return None

# 共通のログインページのルート
@app.route('/login')
def login():
    return render_template('login.html')

# スケジュールをJSONファイルから読み込む
def load_schedule():
    with open('schedule.json', 'r', encoding='utf-8') as f:
        schedule = json.load(f)
    # 各日付の値がリストであることを保証
    for date, schedules in schedule.items():
        if not isinstance(schedules, list):
            schedule[date] = [schedules]
        # 各スケジュールに'id'がない場合は割り当てる
        for schedule_item in schedule[date]:
            if 'id' not in schedule_item:
                schedule_item['id'] = str(uuid.uuid4())
    # スケジュールを保存して、付与した'id'を保存
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(schedule, f, ensure_ascii=False, indent=4)
    # 日付でソート
    def parse_date(date_str):
        return datetime.datetime.strptime(date_str, '%m/%d')
    sorted_schedule = dict(sorted(schedule.items(), key=lambda item: parse_date(item[0])))
    return sorted_schedule

# スケジュールをJSONファイルに保存する
def save_schedule(schedule_dict):
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(schedule_dict, f, ensure_ascii=False, indent=4)

# スケジュールを読み込み
schedule_dict = load_schedule()

# APIエンドポイント: スケジュールを取得する
@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    schedule = load_schedule()
    return jsonify(schedule)

# APIエンドポイント: スケジュールを更新する
@app.route('/api/update_schedule', methods=['POST'])
def update_schedule():
    global schedule_dict
    new_schedule = request.json  # 受け取ったJSONデータを取得
    if new_schedule:
        # 日付をdatetimeオブジェクトに変換して昇順にソート
        sorted_schedule = dict(sorted(new_schedule.items(), key=lambda item: datetime.datetime.strptime(item[0], '%m/%d')))
        
        # 既存のスケジュールを新しいスケジュールで上書き
        schedule_dict = sorted_schedule

        save_schedule(schedule_dict)  # 新しいスケジュールを保存
        print("スケジュールが更新されました。")
        return jsonify({"message": "スケジュールが更新されました。"}), 200
    else:
        return jsonify({"message": "スケジュールの更新に失敗しました。"}), 400

# 一般ユーザー用ログインページのルート
@app.route('/user_login', methods=['POST'])
def user_login():
    password = request.form['user_password']

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

# スケジュールの追加
@app.route('/add', methods=['POST'])
@login_required
def add():
    if not current_user.is_admin:
        flash("管理者のみがスケジュールを追加できます。")
        return redirect(url_for('index'))

    date = request.form['date']
    if platform.system() == 'Windows':
        date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%#m/%#d')
    else:
        date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%-m/%-d')

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

    # ユニークなIDを付与
    new_schedule = {
        "id": str(uuid.uuid4()),
        "plan_type": plan_type,
        "participants": [p.strip() for p in participants],
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "last_updated": now
    }

    if date not in schedule_dict:
        schedule_dict[date] = []

    schedule_dict[date].append(new_schedule)

    # 日付でソート
    def parse_date(date_str):
        return datetime.datetime.strptime(date_str, '%m/%d')
    sorted_schedule = dict(sorted(schedule_dict.items(), key=lambda item: parse_date(item[0])))

    schedule_dict.clear()
    schedule_dict.update(sorted_schedule)

    save_schedule(schedule_dict)
    flash("新しいスケジュールが追加されました。")
    return redirect(url_for('index'))

# スケジュールの編集・削除
@app.route('/manage', methods=['POST'])
@login_required
def manage():
    if not current_user.is_admin:
        flash("管理者のみが編集できます。")
        return redirect(url_for('index'))

    action = request.form.get('action')
    selected_schedule_ids = request.form.getlist('schedule_ids')

    if action == 'edit':
        changes_made = False
        updated_ids = []

        for schedule_id in selected_schedule_ids:
            found = False
            for date, schedule_list in schedule_dict.items():
                for i, schedule_item in enumerate(schedule_list):
                    if schedule_item.get('id') == schedule_id:
                        found = True
                        original = schedule_item

                        plan_type = request.form.get(f'plan_type_{schedule_id}')
                        custom_plan_type = request.form.get(f'custom_plan_type_{schedule_id}')
                        if plan_type == "その他" and custom_plan_type:
                            plan_type = custom_plan_type

                        participants = request.form.getlist(f'participants_{schedule_id}')
                        start_time = request.form.get(f'start_time_{schedule_id}')
                        end_time = request.form.get(f'end_time_{schedule_id}')
                        location = request.form.get(f'location_{schedule_id}')
                        custom_location = request.form.get(f'custom_location_{schedule_id}')
                        if location == "その他" and custom_location:
                            location = custom_location

                        jst = pytz.timezone('Asia/Tokyo')
                        now = datetime.datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')

                        updated = {
                            "id": schedule_id,
                            "plan_type": plan_type,
                            "participants": [p.strip() for p in participants],
                            "start_time": start_time,
                            "end_time": end_time,
                            "location": location,
                            "last_updated": now
                        }

                        if original != updated:
                            schedule_dict[date][i] = updated
                            updated_ids.append(schedule_id)
                            changes_made = True
                        break
                if found:
                    break

        if changes_made:
            save_schedule(schedule_dict)
            flash(f"{len(updated_ids)} 件の変更が保存されました。")
        else:
            flash("変更がありません。")
        return redirect(url_for('index'))

    elif action == 'delete':
        if not selected_schedule_ids:
            flash("削除する予定を選択してください。")
            return redirect(url_for('index'))

        deleted_ids = []

        for schedule_id in selected_schedule_ids:
            found = False
            for date, schedule_list in list(schedule_dict.items()):
                for i, schedule_item in enumerate(schedule_list):
                    if schedule_item.get('id') == schedule_id:
                        del schedule_list[i]
                        deleted_ids.append(schedule_id)
                        found = True
                        break
                if found:
                    if not schedule_list:
                        del schedule_dict[date]
                    break

        if deleted_ids:
            save_schedule(schedule_dict)
            flash(f"{len(deleted_ids)} 件のスケジュールが削除されました。")
        else:
            flash("選択された予定はスケジュールに存在しませんでした。")

        return redirect(url_for('index'))

# フィルタリング機能の修正
@app.route('/filter', methods=['POST'])
@login_required
def filter():
    if 'show_all' in request.form:
        filtered_schedule = schedule_dict
    else:
        selected_participants = request.form.getlist('participants_filter')
        search_mode = request.form.get('search_mode', 'AND')

        if not selected_participants:
            filtered_schedule = schedule_dict
        else:
            filtered_schedule = {}

            for date, schedule_list in schedule_dict.items():
                filtered_list = []
                for details in schedule_list:
                    participants = details.get('participants', [])

                    if "全員" in selected_participants:
                        if "全員" in participants:
                            filtered_list.append(details)
                            continue

                    if search_mode == 'OR':
                        if any(participant in selected_participants for participant in participants):
                            filtered_list.append(details)
                    elif search_mode == 'AND':
                        if all(participant in participants for participant in selected_participants):
                            filtered_list.append(details)
                    if "全員" in participants:
                        filtered_list.append(details)
                if filtered_list:
                    filtered_schedule[date] = filtered_list

    return render_template('index.html', schedule=filtered_schedule, participants_names=PARTICIPANTS_NAMES, user=current_user)

# LINE Webhookのエンドポイント
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# LINEからのメッセージに対する処理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    input_text = event.message.text.strip()
    input_text_lower = input_text.lower()
    
    # 検索モードと名前の初期化
    search_mode = 'OR'  # デフォルトは OR
    names_text = ''
    
    # 'bot help' が入力された場合
    if input_text_lower == 'bot help':
        usage_message = (
            "こんにちは！予定管理botの使い方をご案内します。\n\n"
            "【使い方】\n"
            "・個人の予定を確認する：\n"
            "  bot 名前\n"
            "  例： bot 田中\n\n"
            "・複数名の予定を OR 検索する（いずれかの予定）：\n"
            "  bot 名前1 名前2\n"
            "  例： bot 田中 鈴木\n\n"
            "・複数名の予定を AND 検索する（全員が参加する予定）：\n"
            "  bot and 名前1 名前2\n"
            "  例： bot and 田中 鈴木\n\n"
            "・検索モードを明示的に OR 指定する：\n"
            "  bot or 名前1 名前2\n"
            "  例： bot or 田中 鈴木\n\n"
            "・ヘルプを表示する：\n"
            "  bot help\n\n"
            "※ 名前はスペースで区切って入力してください。\n"
            "※ 大文字・小文字は区別されません。"
        )
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=usage_message)
        )
        return
    
    # メッセージが 'bot and ' で始まるかチェック
    elif input_text_lower.startswith('bot and '):
        search_mode = 'AND'
        names_text = input_text[8:].strip()
    # メッセージが 'bot or ' で始まるかチェック
    elif input_text_lower.startswith('bot or '):
        search_mode = 'OR'
        names_text = input_text[7:].strip()
    # メッセージが 'bot ' で始まる場合
    elif input_text_lower.startswith('bot '):
        search_mode = 'OR'  # デフォルトで OR
        names_text = input_text[4:].strip()
    else:
        # 'bot' で始まらないメッセージには反応しない
        return  # 何もしない

    if not names_text:
        response_message = "名前を入力してください。例: bot 田中"
    else:
        # 入力された名前をスペースで分割してリスト化
        input_names = names_text.split()
        
        # スケジュールをフィルタリングして取得
        filtered_schedule = filter_schedule_by_names(input_names, search_mode)
        
        if filtered_schedule:
            response_message = format_schedule(filtered_schedule)
        else:
            response_message = f"{'、'.join(input_names)}さんの予定が見つかりませんでした。\n詳細はこちらからご確認ください：\nhttps://kyudou-schedule.onrender.com/login"

    # LINEにメッセージを返信
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=response_message)
    )

# 複数の名前でフィルタリングする関数
def filter_schedule_by_names(names, search_mode='OR'):
    filtered_schedule = {}
    names = [name.strip() for name in names]
    for date, events in schedule_dict.items():
        filtered_events = []
        for event in events:
            participants = event.get('participants', [])
            if '全員' in participants:
                filtered_events.append(event)
                continue
            if search_mode == 'OR':
                if any(name in participants for name in names):
                    filtered_events.append(event)
            elif search_mode == 'AND':
                if all(name in participants for name in names):
                    filtered_events.append(event)
        if filtered_events:
            filtered_schedule[date] = filtered_events
    return filtered_schedule

# スケジュールを整形して返す関数
def format_schedule(schedule):
    # スケジュールを整形して返す関数
    result = []
    for date, events in schedule.items():
        for event in events:
            participants = ', '.join(event.get('participants', []))
            # 曜日の取得
            weekday = next_weekday(date)
            result.append(f"{date}（{weekday}）\n予定: {event['plan_type']}\n時間: {event['start_time']}〜{event['end_time']}\n場所: {event['location']}\n参加者: {participants}\n")
    # 結果を結合して、最後にURLを追加
    schedule_text = "\n".join(result)
    schedule_text += "\n詳細はこちらからご確認ください：\nhttps://kyudou-schedule.onrender.com/login"
    return schedule_text

if __name__ == '__main__':
    app.run(debug=True)
