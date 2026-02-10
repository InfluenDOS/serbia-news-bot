import os
import google.generativeai as genai

def debug_models():
    # 从环境变量获取 API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ 错误：未发现 GEMINI_API_KEY 环境变量。请检查 GitHub Secrets 设置。")
        return

    print("🚀 正在初始化 Gemini API...")
    genai.configure(api_key=api_key)

    print("--- 🔍 开始获取可用模型列表 ---")
    try:
        # 获取所有支持当前 Key 的模型
        available_models = genai.list_models()
        
        count = 0
        for m in available_models:
            # 过滤出支持生成内容（generateContent）的模型
            if 'generateContent' in m.supported_generation_methods:
                print(f"✅ 可用模型 ID: {m.name}")
                print(f"   显示名称: {m.display_name}")
                print(f"   支持方法: {m.supported_generation_methods}\n")
                count += 1
        
        if count == 0:
            print("⚠️ 警告：找到了 API，但当前 Key 没有任何可用的生成式模型权限。")
            
    except Exception as e:
        print(f"❌ 获取模型列表失败！详细错误信息：\n{str(e)}")

if __name__ == "__main__":
    debug_models()
