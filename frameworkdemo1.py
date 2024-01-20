import asyncio
import json
import logging
import requests
import random
import sys
import os
import uuid
import base64
import io
from PIL import Image, ImageTk
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.lang import Builder
import httpx
from llama_cpp import Llama
from concurrent.futures import ThreadPoolExecutor
class MainScreen(Screen):
    pass

class SettingsScreen(Screen):
    pass

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

llm = Llama(model_path="llama-2-7b-chat.ggmlv3.q8_0.bin", n_gpu_layers=-1, n_ctx=3900)
executor = ThreadPoolExecutor(max_workers=3)
config = {
    'IMAGE_GENERATION_URL': 'http://127.0.0.1:7860',
    'FOOD_DATABASE': 'food_items.json'
}

KV = '''
ScreenManager:
    MainScreen:
    SettingsScreen:

<MainScreen>:
    name: 'main'
    BoxLayout:
        orientation: 'vertical'
        Image:
            id: img
        Button:
            text: 'Go to Settings'
            on_release: app.root.current = 'settings'

<SettingsScreen>:
    name: 'settings'
    BoxLayout:
        orientation: 'vertical'
        TextInput:
            id: check_in_time
            hint_text: 'Enter Check-in Time'
        TextInput:
            id: check_out_time
            hint_text: 'Enter Check-out Time'
        Button:
            text: 'Save Times and Generate Script'
            on_release:
                app.save_times_and_generate_script(root.ids.check_in_time.text, root.ids.check_out_time.text)
                app.root.current = 'main'
'''


class HaierFridgeApp(App):
    def build(self):
        return Builder.load_string(KV)

    async def suggest_recipes(self):
        food_items = self.load_food_items()
        quantum_state = self.calculate_quantum_state_based_on_food(food_items)
        recipe_suggestion = await self.generate_recipe_suggestion(food_items, quantum_state)
        self.display_recipe_suggestion(recipe_suggestion)

    def load_food_items(self):
        with open(config['FOOD_DATABASE'], 'r') as file:
            return json.load(file)

    def calculate_quantum_state_based_on_food(self, food_items):
        return hash(str(food_items)) % 10

    async def generate_recipe_suggestion(self, food_items, quantum_state):
        prompt = f"Generate a recipe based on food items {food_items} and quantum state {quantum_state}"
        response = llm(prompt, max_tokens=200)
        return response['choices'][0]['text'] if response['choices'] else None

    def display_recipe_suggestion(self, recipe_suggestion):
        pass

    async def generate_image(self, prompt):
        payload = self.prepare_image_generation_payload(prompt)
        try:
            response = requests.post(config['IMAGE_GENERATION_URL'], json=payload)
            if response.status_code == 200:
                return self.process_image_response(response)
            else:
                logger.error(f"Error generating image: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"Error in generate_image: {e}")
        return None

    def prepare_image_generation_payload(self, message):
        return {
            "prompt": message,
            "steps": 51,
            "seed": random.randrange(sys.maxsize),
            "enable_hr": "false",
            "denoising_strength": "0.7",
            "cfg_scale": "7",
            "width": 526,
            "height": 756,
            "restore_faces": "true",
        }

    def process_image_response(self, response):
        try:
            image_data = response.json().get('images', [])
            return [self.convert_base64_to_tk(img_data) for img_data in image_data if img_data]
        except Exception as e:
            logger.error(f"Error processing image data: {e}")
            return []

    def convert_base64_to_tk(self, base64_data):
        if ',' in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        image_data = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_data))
        return ImageTk.PhotoImage(image)

    def display_images(self, images):
        for img in images:
            self.root.get_screen('main').ids.img.source = img
            Clock.schedule_once(lambda dt: None, 5)

if __name__ == '__main__':
    HaierFridgeApp().run()
