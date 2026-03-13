from PIL import Image
import os

def convert_png_to_ico(png_path, ico_path):
    img = Image.open(png_path)
    # 아이콘에 적합한 사이즈로 변환 (표준 사이즈들 포함)
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format='ICO', sizes=icon_sizes)
    print(f"Converted {png_path} to {ico_path}")

if __name__ == "__main__":
    convert_png_to_ico("app_icon.png", "app_icon.ico")
