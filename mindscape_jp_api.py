# mindscape-jp - 日本語診断 + Midjourney連携 API
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import openai
import json
import asyncio
import aiohttp
import time
from datetime import datetime
import os
import re

# FastAPI初期化
app = FastAPI(
    title="Mindscape Japan API",
    description="日本語心理診断 + Midjourney連携システム",
    version="1.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 環境変数設定
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")

# OpenAI設定
if OPENAI_API_KEY and OPENAI_API_KEY.startswith("sk-"):
    openai.api_key = OPENAI_API_KEY
    OPENAI_ENABLED = True
    print(f"🧠 OpenAI API設定済み: {OPENAI_API_KEY[:8]}...")
else:
    OPENAI_ENABLED = False
    print("⚠️  OpenAI API未設定")

# Discord設定確認
DISCORD_ENABLED = bool(DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID)
print(f"🎨 Discord/Midjourney: {'有効' if DISCORD_ENABLED else '無効'}")

# データモデル
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

class MidjourneyRequest(BaseModel):
    heart_landscape: str
    user_name: str

# ストレージ
generated_images = {}  # {user_name: image_url}
assessment_data = {}   # {user_name: assessment_data}

# 🎨 心象風景 → Midjourneyプロンプト生成
async def generate_image_prompt(heart_landscape: str, user_name: str = "") -> str:
    """心象風景を美しいMidjourneyプロンプトに変換"""
    
    if not OPENAI_ENABLED:
        return f"Beautiful artistic landscape inspired by: {heart_landscape[:100]}, serene atmosphere, professional illustration style, high quality, 4K"
    
    prompt_request = f"""
以下の心象風景を、美しいMidjourneyプロンプトに変換してください：

心象風景: "{heart_landscape}"

要件:
- 美しく芸術的な表現
- 感情的な本質を捉える
- Midjourney向けの適切な記述
- ネガティブすぎる表現は避けて美しい表現に変換
- 英語でプロンプト作成
- 高品質な画像生成用のキーワード追加

1行のプロンプトのみを回答してください。
"""

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert at creating beautiful Midjourney prompts that capture emotional landscapes."},
                {"role": "user", "content": prompt_request}
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        prompt = response.choices[0].message.content.strip()
        
        # 高品質キーワード追加
        quality_tags = ", beautiful lighting, artistic composition, high quality, 4K, professional photography style"
        final_prompt = prompt + quality_tags
        
        return final_prompt
        
    except Exception as e:
        print(f"🚨 プロンプト生成エラー: {e}")
        return f"Beautiful artistic landscape inspired by {heart_landscape[:50]}, serene atmosphere, high quality, 4K"

# 🤖 Discord/Midjourney連携
async def send_to_midjourney(prompt: str, user_name: str) -> bool:
    """Discord経由でMidjourneyにプロンプト送信"""
    
    if not DISCORD_ENABLED:
        print("🎨 [デモモード] Discord設定なし")
        # デモ用画像をセット
        await asyncio.sleep(2)
        generated_images[user_name] = "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop"
        return True
    
    try:
        url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
        headers = {
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Midjourneyコマンド送信
        data = {"content": f"/imagine prompt: {prompt}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    message_id = result.get("id")
                    
                    print(f"✅ Midjourney生成開始: {user_name}")
                    print(f"📝 プロンプト: {prompt[:50]}...")
                    
                    # バックグラウンドで画像監視開始
                    asyncio.create_task(monitor_image_generation(message_id, user_name))
                    return True
                else:
                    print(f"❌ Discord API エラー: {response.status}")
                    return False
                    
    except Exception as e:
        print(f"❌ Midjourney連携エラー: {e}")
        return False

async def monitor_image_generation(message_id: str, user_name: str, timeout: int = 300):
    """Discordチャンネルで画像生成完了を監視"""
    
    start_time = time.time()
    print(f"👁️ 画像監視開始: {user_name}")
    
    while time.time() - start_time < timeout:
        try:
            url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
            headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        messages = await response.json()
                        
                        for message in messages:
                            # Midjourneyからの返信メッセージを探す
                            if (message.get("reference") and 
                                message["reference"].get("message_id") == message_id and
                                message.get("attachments")):
                                
                                for attachment in message["attachments"]:
                                    if attachment.get("content_type", "").startswith("image/"):
                                        image_url = attachment.get("url")
                                        generated_images[user_name] = image_url
                                        print(f"🎨 画像生成完了: {user_name}")
                                        print(f"🔗 画像URL: {image_url}")
                                        return image_url
            
            await asyncio.sleep(10)  # 10秒ごとにチェック
            
        except Exception as e:
            print(f"🚨 画像監視エラー: {e}")
            await asyncio.sleep(10)
    
    print(f"⏰ 画像監視タイムアウト: {user_name}")
    return None

# 🧠 簡易心理分析（日本語対応）
async def analyze_japanese_responses(quiet_responses: List[str], heart_landscape: str, profile: UserProfile) -> dict:
    """日本語回答の簡易分析"""
    
    if not OPENAI_ENABLED:
        return {
            "overview": f"{profile.name}さんの心理状態は安定しています。",
            "mood": "穏やか",
            "energy": "バランス良好",
            "recommendations": ["定期的な休息", "適度な運動", "趣味の時間"]
        }
    
    analysis_prompt = f"""
以下の日本語回答を分析して、簡潔な心理アセスメントを作成してください。

プロフィール: {profile.name}さん、{profile.age}歳、{profile.department}
心象風景: {heart_landscape}

自由回答:
{chr(10).join([f"{i+1}. {resp}" for i, resp in enumerate(quiet_responses) if resp.strip()])}

以下のJSON形式で回答してください：
{{
    "overview": "全体的な心理状態（1-2行）",
    "mood": "気分（一言）",
    "energy": "エネルギーレベル（一言）", 
    "recommendations": ["推奨事項1", "推奨事項2", "推奨事項3"]
}}

日本語で、優しく支援的なトーンで分析してください。
"""

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは優しい心理カウンセラーです。"},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        result_text = response.choices[0].message.content
        return json.loads(result_text)
        
    except Exception as e:
        print(f"🚨 分析エラー: {e}")
        return {
            "overview": f"{profile.name}さんの心理状態は安定しています。",
            "mood": "穏やか",
            "energy": "バランス良好", 
            "recommendations": ["定期的な休息", "適度な運動", "趣味の時間"]
        }

# 📋 API エンドポイント

@app.post("/api/generate-image")
async def generate_image(request: MidjourneyRequest, background_tasks: BackgroundTasks):
    """心象風景からMidjourney画像生成"""
    
    try:
        print(f"🎨 画像生成リクエスト: {request.user_name}")
        print(f"💭 心象風景: {request.heart_landscape[:50]}...")
        
        # プロンプト生成
        prompt = await generate_image_prompt(request.heart_landscape, request.user_name)
        print(f"📝 生成プロンプト: {prompt[:100]}...")
        
        # Midjourney送信
        success = await send_to_midjourney(prompt, request.user_name)
        
        if success:
            return {
                "status": "success",
                "message": "画像生成を開始しました",
                "prompt": prompt,
                "user_name": request.user_name
            }
        else:
            raise HTTPException(status_code=500, detail="Midjourney送信に失敗しました")
            
    except Exception as e:
        print(f"❌ 画像生成エラー: {e}")
        raise HTTPException(status_code=500, detail=f"画像生成失敗: {str(e)}")

@app.get("/api/image-status/{user_name}")
async def get_image_status(user_name: str):
    """画像生成状況確認"""
    
    if user_name in generated_images:
        return {
            "status": "completed",
            "image_url": generated_images[user_name],
            "user_name": user_name
        }
    else:
        return {
            "status": "generating",
            "message": "画像生成中...",
            "user_name": user_name
        }

@app.post("/api/process-assessment")
async def process_assessment(request: AssessmentRequest, background_tasks: BackgroundTasks):
    """日本語診断データ処理 + 画像生成"""
    
    try:
        print(f"📊 診断処理開始: {request.profile.name}")
        
        # 診断データ保存
        assessment_data[request.profile.name] = request.dict()
        
        # 簡易分析
        analysis = await analyze_japanese_responses(
            request.quiet_responses, 
            request.heart_landscape, 
            request.profile
        )
        
        # バックグラウンドで画像生成開始
        background_tasks.add_task(
            start_image_generation, 
            request.heart_landscape, 
            request.profile.name
        )
        
        return {
            "status": "success",
            "profile": request.profile.dict(),
            "analysis": analysis,
            "message": "診断処理完了。画像生成を開始しました。"
        }
        
    except Exception as e:
        print(f"❌ 診断処理エラー: {e}")
        raise HTTPException(status_code=500, detail=f"診断処理失敗: {str(e)}")

async def start_image_generation(heart_landscape: str, user_name: str):
    """バックグラウンド画像生成タスク"""
    try:
        prompt = await generate_image_prompt(heart_landscape, user_name)
        await send_to_midjourney(prompt, user_name)
    except Exception as e:
        print(f"❌ バックグラウンド画像生成エラー: {e}")

@app.get("/api/assessment/{user_name}")
async def get_assessment(user_name: str):
    """診断データ取得"""
    
    if user_name in assessment_data:
        return {
            "status": "success",
            "data": assessment_data[user_name],
            "image_url": generated_images.get(user_name)
        }
    else:
        raise HTTPException(status_code=404, detail="診断データが見つかりません")

@app.get("/health")
async def health_check():
    """ヘルスチェック"""
    return {
        "status": "healthy",
        "service": "Mindscape Japan API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "openai_enabled": OPENAI_ENABLED,
        "discord_enabled": DISCORD_ENABLED,
        "total_assessments": len(assessment_data),
        "generated_images": len(generated_images)
    }

@app.get("/")
async def root():
    """API情報"""
    return {
        "message": "Mindscape Japan API - 日本語心理診断 + Midjourney連携",
        "endpoints": {
            "/api/generate-image": "画像生成",
            "/api/image-status/{user_name}": "画像状況確認", 
            "/api/process-assessment": "診断処理",
            "/health": "ヘルスチェック"
        },
        "status": {
            "openai": "有効" if OPENAI_ENABLED else "無効",
            "discord": "有効" if DISCORD_ENABLED else "無効"
        }
    }

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Mindscape Japan API 起動中...")
    print(f"🧠 OpenAI: {'有効' if OPENAI_ENABLED else '無効'}")
    print(f"🎨 Discord/Midjourney: {'有効' if DISCORD_ENABLED else '無効'}")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)