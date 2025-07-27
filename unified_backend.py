# 完全統合版 Mindscape Diagnosis Backend
# 全機能統合：診断システム + 管理システム + API連携

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import openai
import json
import asyncio
import aiohttp
import time
from datetime import datetime, timedelta
import os
import re
import uuid
from pathlib import Path

# ========================================
# 🔑 API KEY 設定エリア（環境変数対応）
# ========================================

# 環境変数から取得
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")

# システム設定
SYSTEM_NAME = "Mindscape Diagnosis Enterprise"
ADMIN_EMAIL = "admin@yourcompany.com"

# Render URL（本番時は自動で設定される）
def get_base_url():
    try:
        # Renderの場合、環境変数から取得
        render_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_url:
            return render_url
        
        # ローカル開発環境
        return "http://localhost:8001"
    except:
        return "http://localhost:8001"

BASE_URL = get_base_url()

# OpenAI API設定
if OPENAI_API_KEY and OPENAI_API_KEY.startswith("sk-"):
    openai.api_key = OPENAI_API_KEY
    OPENAI_ENABLED = True
    print(f"🧠 OpenAI API Key設定済み: {OPENAI_API_KEY[:8]}...")
else:
    OPENAI_ENABLED = False
    print("⚠️  OpenAI API Key未設定 - フォールバック分析を使用")

# Discord設定チェック
DISCORD_ENABLED = bool(DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID)
if DISCORD_ENABLED:
    print("🎨 Discord/Midjourney: 有効")
else:
    print("⚠️  Discord/Midjourney: 無効（デモ画像使用）")

print(f"🧠 OpenAI有効: {OPENAI_ENABLED}")

# ========================================
# 🔧 保存機能追加（GPTの解決策）
# ========================================

def save_result(user_id, answers, gpt_result):
    """診断結果を保存する関数"""
    try:
        with open("results.json", "a", encoding="utf-8") as f:
            json.dump({
                "id": user_id,
                "answers": answers,
                "result": gpt_result,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False)
            f.write("\n")  # JSONを1行ずつ保存するため
        print(f"✅ 結果保存完了: {user_id}")
    except Exception as e:
        print(f"❌ 保存エラー: {e}")

# ========================================
# FastAPI アプリケーション初期化
# ========================================

app = FastAPI(
    title=SYSTEM_NAME,
    description="企業向け心理診断システム - 統合版",
    version="2.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイル配信（サンプル画像用）
app.mount("/ms_mj_sample0", StaticFiles(directory="ms_mj_sample0"), name="sample_images")

# ========================================
# データモデル定義
# ========================================

class UserProfile(BaseModel):
    name: str
    age: int
    department: str

class AssessmentRequest(BaseModel):
    profile: UserProfile
    answers: List[str]
    timestamp: str
    department_questions: List[str]
    quiet_responses: List[str]
    heart_landscape: str

class QuietAnalysisResult(BaseModel):
    overview: str
    characteristics: List[str]
    quiet_analysis: str
    diagnostic_tags: List[str]
    alert_indicators: List[str]

class AssessmentResult(BaseModel):
    profile: UserProfile
    quiet_analysis: QuietAnalysisResult
    final_diagnosis: str
    alert: bool
    alert_reason: Optional[str]
    image_prompt: str
    image_url: Optional[str]
    timestamp: str

class Employee(BaseModel):
    id: Optional[int] = None
    name: str
    email: str
    department: str
    role: str
    status: str = "pending"
    assessment_date: Optional[datetime] = None
    invited_date: datetime
    assessment_link: Optional[str] = None

# ========================================
# データストレージ
# ========================================

assessment_results = []
alert_records = []
employees = []
assessment_links = {}

# サンプルデータ初期化
def initialize_sample_data():
    global employees
    sample_employees = [
        {
            "id": 1,
            "name": "Morgan Williams",
            "email": "williams@company.com",
            "department": "sales",
            "role": "Sales Manager",
            "status": "completed",
            "assessment_date": datetime.now() - timedelta(days=2),
            "invited_date": datetime.now() - timedelta(days=7)
        },
        {
            "id": 2,
            "name": "Jamie Chen",
            "email": "chen@company.com",
            "department": "tech",
            "role": "Senior Developer", 
            "status": "pending",
            "assessment_date": None,
            "invited_date": datetime.now() - timedelta(days=3)
        },
        {
            "id": 3,
            "name": "Riley Park",
            "email": "park@company.com",
            "department": "general",
            "role": "HR Specialist",
            "status": "overdue",
            "assessment_date": None,
            "invited_date": datetime.now() - timedelta(days=10)
        }
    ]
    
    for emp_data in sample_employees:
        employees.append(Employee(**emp_data))

# ========================================
# 心理分析エンジン
# ========================================

async def analyze_quiet_responses(quiet_responses: List[str], profile: UserProfile) -> QuietAnalysisResult:
    """QuietGPT分析エンジン"""
    
    print(f"🧠 分析開始: {profile.name} (OpenAI有効: {OPENAI_ENABLED})")
    
    if not OPENAI_ENABLED:
        print("⚠️  OpenAI無効 - フォールバック分析使用")
        return fallback_analysis(quiet_responses, profile)
    
    responses_text = "\n\n".join([
        f"Response {i+11}: {response}" 
        for i, response in enumerate(quiet_responses) 
        if response.strip()
    ])
    
    quiet_prompt = f"""
あなたは企業の心理アセスメントシステムです。
以下の従業員の自由回答を分析し、心理状態を評価してください。

従業員プロフィール:
- 名前: {profile.name}
- 年齢: {profile.age}
- 部署: {profile.department}

自由回答（質問11-19）:
{responses_text}

以下のJSON形式で回答してください：
{{
    "overview": "全体的な心理状態の1-2行要約",
    "characteristics": ["特徴1", "特徴2", "特徴3"],
    "quiet_analysis": "詳細な心理分析（3-4文）",
    "diagnostic_tags": ["タグ1", "タグ2", "タグ3"],
    "alert_indicators": ["懸念事項1", "懸念事項2"] or []
}}

重点分析項目:
- ストレス指標と燃え尽き症候群の兆候
- コミュニケーションスタイルと防御機制
- 職場適応度と人間関係
- 支援が必要な領域の特定
"""

    try:
        print(f"🧠 OpenAI API呼び出し中: {profile.name}")
        
        # OpenAI API呼び出し（0.28対応）
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは経験豊富な産業心理学者です。"},
                {"role": "user", "content": quiet_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        result_text = response.choices[0].message.content
        
        print(f"✅ OpenAI API応答受信: {profile.name}")
        
        # JSON解析
        try:
            result_data = json.loads(result_text)
            print(f"✅ JSON解析成功: {profile.name}")
            return QuietAnalysisResult(**result_data)
        except json.JSONDecodeError as e:
            print(f"⚠️  JSON解析失敗: {e} - フォールバック使用")
            return fallback_analysis(quiet_responses, profile)
            
    except Exception as e:
        print(f"❌ OpenAI API エラー: {e}")
        print("🔄 フォールバック分析に切り替え")
        return fallback_analysis(quiet_responses, profile)

def fallback_analysis(quiet_responses: List[str], profile: UserProfile) -> QuietAnalysisResult:
    """OpenAI失敗時のフォールバック分析"""
    
    all_text = " ".join(quiet_responses).lower()
    
    # 感情キーワード分析
    stress_keywords = ["疲れ", "ストレス", "忙しい", "大変", "辛い", "きつい", "overwhelmed", "tired", "stressed"]
    positive_keywords = ["楽しい", "やりがい", "満足", "成長", "好き", "happy", "satisfied", "motivated"]
    concern_keywords = ["不安", "心配", "困る", "悩み", "問題", "anxious", "worried", "concerned"]
    
    stress_count = sum(1 for word in stress_keywords if word in all_text)
    positive_count = sum(1 for word in positive_keywords if word in all_text)
    concern_count = sum(1 for word in concern_keywords if word in all_text)
    
    # 部署別特化分析
    dept_insights = {
        "sales": ("営業職特有のプレッシャー", "顧客対応と目標達成のバランス"),
        "tech": ("技術的挑戦への取り組み", "技術革新への適応度"),
        "creative": ("創造性と表現力", "アーティスティックな満足度"),
        "manager": ("リーダーシップと責任", "チーム運営の課題"),
        "general": ("業務への取り組み", "組織での役割認識")
    }
    
    dept_info = dept_insights.get(profile.department, ("業務への取り組み", "職場での適応"))
    
    if stress_count > positive_count or concern_count > 1:
        return QuietAnalysisResult(
            overview=f"{profile.department}部門での業務において、現在心理的な負荷が確認されます。",
            characteristics=["高い責任感", "率直な問題意識", "改善への意欲"],
            quiet_analysis=f"{profile.name}様の回答から、{dept_info[0]}において一定の心理的負荷が読み取れます。{dept_info[1]}に関する懸念が表れており、適切なサポートが必要と考えられます。",
            diagnostic_tags=["support_needed", "stress_management", "follow_up_required"],
            alert_indicators=["高いストレスレベル", "他人とのコミュニケーションからの遠ざかり"]
        )
    else:
        return QuietAnalysisResult(
            overview=f"{profile.department}部門での業務において、安定した心理状態が確認されます。",
            characteristics=["バランスの取れた視点", "前向きな姿勢", "安定した適応"],
            quiet_analysis=f"{profile.name}様の回答から、{dept_info[0]}において健全な職場適応が確認されます。{dept_info[1]}に対する前向きな取り組みが見られ、現在の良好な状態の維持が推奨されます。",
            diagnostic_tags=["stable_state", "positive_adaptation", "maintenance_focus"],
            alert_indicators=[]
        )

# アラート評価システム
def evaluate_sas_alert(quiet_analysis: QuietAnalysisResult, heart_landscape: str) -> tuple[bool, str]:
    """SAS（Soft Alert Signal）評価"""
    
    alert_indicators = []
    
    # QuietGPT分析からの警告
    if quiet_analysis.alert_indicators:
        alert_indicators.extend(quiet_analysis.alert_indicators)
    
    # 診断タグからのリスク評価
    risk_tags = ["support_needed", "stress_management", "follow_up_required", "burnout_risk"]
    if any(tag in quiet_analysis.diagnostic_tags for tag in risk_tags):
        alert_indicators.append("リスク指標が検出されました")
    
    # Heart landscapeの感情分析
    heart_lower = heart_landscape.lower()
    concerning_words = ["暗い", "嵐", "空虚", "冷たい", "重い", "壊れた", "孤独", "dark", "storm", "empty", "cold", "broken"]
    
    if any(word in heart_lower for word in concerning_words):
        alert_indicators.append("心象風景に懸念要素が含まれています")
    
    # アラート判定
    if len(alert_indicators) >= 2:
        return True, f"複数の懸念指標: {'; '.join(alert_indicators[:3])}"
    elif any("重要" in indicator or "severe" in indicator.lower() for indicator in alert_indicators):
        return True, f"重要な指標: {alert_indicators[0]}"
    else:
        return False, ""

# 画像プロンプト生成
async def generate_image_prompt(heart_landscape: str, quiet_analysis: QuietAnalysisResult) -> str:
    """Midjourney用画像プロンプト生成"""
    
    if not OPENAI_ENABLED:
        return f"Beautiful artistic landscape inspired by: {heart_landscape[:100]}, serene atmosphere, professional illustration style"
    
    prompt_request = f"""
以下の心象風景を美しいアート作品のプロンプトに変換してください：

心象風景: "{heart_landscape}"
心理状態: {quiet_analysis.overview}

以下の要件で1行のプロンプトを作成：
- 美しく芸術的な表現
- 感情的な本質を捉える
- Midjourney向けの適切な記述
- ネガティブすぎる表現は避ける

プロンプトのみを回答してください。
"""

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは美しい画像プロンプトを作成する専門家です。"},
                {"role": "user", "content": prompt_request}
            ],
            temperature=0.7,
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"画像プロンプト生成エラー: {e}")
        return f"Beautiful landscape inspired by {heart_landscape[:50]}, artistic style, serene mood"

# 最終診断生成
async def generate_final_diagnosis(quiet_analysis: QuietAnalysisResult, profile: UserProfile) -> str:
    """最終診断レポート生成"""
    
    if not OPENAI_ENABLED:
        return f"""
## {profile.name}様の心理アセスメント結果

### 全体評価
{quiet_analysis.overview}

### 主要特徴
{chr(10).join(f'• {char}' for char in quiet_analysis.characteristics)}

### 詳細分析
{quiet_analysis.quiet_analysis}

### 推奨事項
{'心理的負荷が確認されているため、適切なサポートとフォローアップをお勧めします。' if quiet_analysis.alert_indicators else '現在の良好な状態を維持するため、定期的なセルフケアの継続をお勧めします。'}
        """.strip()
    
    diagnosis_prompt = f"""
以下の心理分析結果に基づき、企業向けの専門的な診断レポートを作成してください：

従業員: {profile.name}（{profile.age}歳、{profile.department}部門）

分析結果:
- 概要: {quiet_analysis.overview}
- 特徴: {', '.join(quiet_analysis.characteristics)}
- 詳細分析: {quiet_analysis.quiet_analysis}
- 診断タグ: {', '.join(quiet_analysis.diagnostic_tags)}

以下の構成でレポートを作成：
1. エグゼクティブサマリー
2. 主要な発見事項
3. 推奨事項
4. 次のステップ

専門的だが支援的なトーンで記述してください。
"""

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは企業の産業心理学者です。"},
                {"role": "user", "content": diagnosis_prompt}
            ],
            temperature=0.6,
            max_tokens=800
        )
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"診断生成エラー: {e}")
        return f"専門的な評価が完了しました。{profile.name}様の結果について、個別の相談をお勧めします。"

# ========================================
# Midjourney連携（Discord）
# ========================================

async def send_to_midjourney(prompt: str) -> Optional[str]:
    """Discord/Midjourney連携"""
    
    if not DISCORD_ENABLED:
        print("🎨 [デモモード] Midjourney: Discord設定なし")
        return "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop"
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
        headers = {
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        
        data = {"content": f"/imagine prompt: {prompt}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    print("✅ Midjourney生成開始")
                    await asyncio.sleep(2)
                    return "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop"
                else:
                    print(f"❌ Discord API エラー: {response.status}")
                    return None
                    
    except Exception as e:
        print(f"❌ Midjourney連携エラー: {e}")
        return None

# ========================================
# 🆕 強化版API エンドポイント
# ========================================

@app.get("/api/results")
async def get_all_results():
    """全診断結果を取得（GPT推奨版）"""
    try:
        results = []
        with open("results.json", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        
        return {
            "status": "success",
            "data": results,
            "count": len(results),
            "timestamp": datetime.now().isoformat()
        }
    except FileNotFoundError:
        return {
            "status": "success", 
            "data": [], 
            "count": 0,
            "message": "まだ診断結果がありません"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"データ読み取りエラー: {str(e)}")

@app.get("/api/results/summary")
async def get_results_summary():
    """診断結果サマリー"""
    try:
        results = []
        with open("results.json", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        
        # 統計計算
        total_count = len(results)
        alert_count = sum(1 for r in results if r.get('result', {}).get('alert', False))
        departments = {}
        
        for result in results:
            dept = result.get('result', {}).get('profile', {}).get('department', 'Unknown')
            departments[dept] = departments.get(dept, 0) + 1
        
        return {
            "total_assessments": total_count,
            "alert_cases": alert_count,
            "alert_rate": round((alert_count / total_count * 100), 1) if total_count > 0 else 0,
            "department_breakdown": departments,
            "latest_assessment": results[-1].get('timestamp') if results else None
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/results/alerts")
async def get_alert_cases():
    """アラート案件のみ取得"""
    try:
        alerts = []
        with open("results.json", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    result = json.loads(line)
                    if result.get('result', {}).get('alert', False):
                        alerts.append({
                            "name": result.get('id'),
                            "timestamp": result.get('timestamp'),
                            "department": result.get('result', {}).get('profile', {}).get('department'),
                            "alert_reason": result.get('result', {}).get('alert_reason'),
                            "overview": result.get('result', {}).get('quiet_analysis', {}).get('overview')
                        })
        
        return {
            "status": "success",
            "alerts": alerts,
            "count": len(alerts)
        }
        
    except Exception as e:
        return {"error": str(e)}

# ========================================
# 🆕 CSV読み込み機能追加
# ========================================

@app.get("/api/export")
async def export_results():
    """保存された結果をCSV形式でエクスポート"""
    try:
        results = []
        with open("results.json", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        
        return {"status": "success", "data": results, "count": len(results)}
    except FileNotFoundError:
        return {"status": "success", "data": [], "count": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"エクスポートエラー: {str(e)}")

# ========================================
# API エンドポイント
# ========================================

@app.post("/api/process-assessment")
async def process_assessment(request: AssessmentRequest, background_tasks: BackgroundTasks) -> AssessmentResult:
    try:
        print(f"🚀 診断処理開始: {request.profile.name}")

        # QuietGPT 分析
        quiet_analysis = await analyze_quiet_responses(request.quiet_responses, request.profile)

        # アラート評価
        alert_flag, alert_reason = evaluate_sas_alert(quiet_analysis, request.heart_landscape)

        # 画像プロンプト
        image_prompt = await generate_image_prompt(request.heart_landscape, quiet_analysis)

        # 最終診断
        final_diagnosis = await generate_final_diagnosis(quiet_analysis, request.profile)

        # 結果構造
        result = AssessmentResult(
            profile=request.profile,
            quiet_analysis=quiet_analysis,
            final_diagnosis=final_diagnosis,
            alert=alert_flag,
            alert_reason=alert_reason if alert_flag else None,
            image_prompt=image_prompt,
            image_url=None,
            timestamp=datetime.now().isoformat()
        )

        # 🔧 保存（修正済み！）
        save_result(user_id=request.profile.name, answers=request.answers, gpt_result=result.dict())

        # Midjourney（仮画像用）
        background_tasks.add_task(send_to_midjourney, image_prompt)

        # アラート記録
        if alert_flag:
            alert_records.append({
                "profile": request.profile.dict(),
                "alert_reason": alert_reason,
                "quiet_analysis": quiet_analysis.dict(),
                "timestamp": datetime.now().isoformat()
            })

        print(f"✅ 診断完了: {request.profile.name}")
        return result

        
    except Exception as e:
        print(f"❌ 診断処理エラー: {e}")
        raise HTTPException(status_code=500, detail=f"診断処理失敗: {str(e)}")

# 結果取得
@app.get("/api/result/{user_name}")
async def get_result(user_name: str):
    """診断結果取得"""
    for result in assessment_results:
        if result["profile"]["name"] == user_name:
            return result
    
    raise HTTPException(status_code=404, detail="結果が見つかりません")

# ========================================
# HTMLファイル配信
# ========================================

@app.get("/", response_class=HTMLResponse)
async def serve_management():
    """管理画面HTML配信"""
    return HTMLResponse("""
    <html>
    <body>
    <h1>Mindscape Diagnosis - Management</h1>
    <p>管理画面は準備中です</p>
    <p><a href="/index.html">診断画面へ</a></p>
    </body>
    </html>
    """)

@app.get("/index.html", response_class=HTMLResponse) 
async def serve_assessment():
    """診断画面HTML配信"""
    try:
        with open("index.html", 'r', encoding='utf-8') as f:
            content = f.read()
        return HTMLResponse(content)
    except FileNotFoundError:
        return HTMLResponse("""
        <html>
        <body>
        <h1>診断ファイルが見つかりません</h1>
        <p>index.html が見つかりません</p>
        </body>
        </html>
        """)

# ========================================
# システム管理
# ========================================

@app.get("/health")
async def health_check():
    """ヘルスチェック"""
    return {
        "status": "healthy",
        "service": SYSTEM_NAME,
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "total_assessments": len(assessment_results),
        "total_alerts": len(alert_records),
        "openai_enabled": OPENAI_ENABLED,
        "discord_enabled": DISCORD_ENABLED,
        "features": {
            "gpt_analysis": OPENAI_ENABLED,
            "midjourney_integration": DISCORD_ENABLED,
            "assessment": True,
            "alerts": True,
            "save_results": True,
            "export_csv": True
        }
    }

# ========================================
# アプリケーション起動
# ========================================

if __name__ == "__main__":
    import uvicorn
    
    # 初期化
    initialize_sample_data()
    
    # 設定確認
    print("=" * 50)
    print(f"🚀 {SYSTEM_NAME} 起動中...")
    print("=" * 50)
    
    if OPENAI_ENABLED:
        print("🧠 OpenAI GPT-4 分析: 有効")
    else:
        print("⚠️  OpenAI API: 無効（フォールバック分析使用）")
    
    if DISCORD_ENABLED:
        print("🎨 Discord/Midjourney: 有効")
    else:
        print("⚠️  Discord/Midjourney: 無効（デモ画像使用）")
    
    print(f"🌐 診断画面: http://localhost:8001/index.html")
    print(f"📊 ヘルスチェック: http://localhost:8001/health")
    print(f"📁 結果エクスポート: http://localhost:8001/api/export")
    print("=" * 50)
    
    # サーバー起動
    uvicorn.run(app, host="0.0.0.0", port=8001)
