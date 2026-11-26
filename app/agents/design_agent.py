import re
from typing import List, Dict, Any, Optional

class DesignAgent:
    """
    Dedicated Visual & Design Agent:
    Specializes in visual art direction, character consistency, and scene aesthetic framing.
    Translates script concepts and user design inputs into structured, high-detail prompts for AI rendering.
    Dynamically infers characters, environments, visual actions, and facial motions from narration and script context.
    """

    STYLE_PRESETS = {
        "cinematic_realistic": {
            "name": "Realistic Educational Cinema",
            "aesthetic": "Photorealistic cinematic educational film still, natural authentic human features, shot on 35mm Arri Alexa lens, cinematic depth of field, clear natural lighting",
            "render_suffix": "photorealistic educational visual, 8k resolution, cinematic documentary still, 16:9 widescreen composition, beautifully proportioned character anatomy, clean visual without text or typography"
        },
        "pixar_3d": {
            "name": "3D Pixar / Disney 3D",
            "aesthetic": "3D Disney Pixar animated film aesthetic, soft expressive character lighting, vibrant warm studio lighting, Octane render 8K, high quality character animation render",
            "render_suffix": "Disney Pixar animation style, highly detailed 3D render, 16:9 widescreen composition, cinematic depth of field, adorable expressive stylized character design, beautifully proportioned symmetrical face with two bright expressive eyes and cute button nose, flawless facial anatomy, clean visual without text"
        },
        "storybook_watercolor": {
            "name": "Vintage Watercolor Storybook",
            "aesthetic": "Classic children's storybook illustration, whimsical soft watercolor washes, delicate ink line art, gentle pastel color palette",
            "render_suffix": "watercolor and ink illustration, vintage storybook art, high resolution, 16:9 widescreen, charming illustrative composition, clean visual without text"
        },
        "anime_ghibli": {
            "name": "Japanese Anime (Studio Ghibli)",
            "aesthetic": "Studio Ghibli inspired anime aesthetic, hand-drawn animation lines, Makoto Shinkai vibrant sky and lighting, lush painted textures",
            "render_suffix": "Japanese animation masterpiece, vibrant anime aesthetic, 16:9 widescreen, expressive character art, clean visual without text"
        },
        "claymation": {
            "name": "Claymation & Stop-Motion",
            "aesthetic": "Handcrafted claymation character, tactile clay surface textures, charming sculpted details, miniature physical tabletop set, Aardman style stop-motion aesthetic",
            "render_suffix": "physical clay sculpture, stop-motion animation frame, warm tactile lighting, 16:9 widescreen, charming tactile composition, clean visual without text"
        },
        "cyberpunk_scifi": {
            "name": "Futuristic Sci-Fi & Cyberpunk",
            "aesthetic": "Futuristic sci-fi concept art, sleek augmented details, volumetric blue and amber lighting, state-of-the-art holographic interface",
            "render_suffix": "futuristic sci-fi concept art, Octane render, volumetric atmosphere, 16:9 widescreen, clean visual without text"
        }
    }

    def get_available_styles(self) -> List[Dict[str, str]]:
        """Returns the list of selectable visual design styles."""
        return [
            {"id": key, "name": val["name"]}
            for key, val in self.STYLE_PRESETS.items()
        ]

    def design_scenes(
        self,
        scenes: List[Dict[str, Any]],
        style_id: str = "pixar_3d",
        custom_character: Optional[str] = None,
        custom_environment: Optional[str] = None,
        custom_design_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Takes raw scenes from ScriptAgent and crafts contextually accurate visual prompts,
        motion prompts, and camera movements conforming to the script's actual topic.
        Default style is 3D Pixar Animation.
        """
        style = self.STYLE_PRESETS.get(style_id, self.STYLE_PRESETS["pixar_3d"])
        auto_motions = ["zoom_in", "pan_right", "zoom_out", "pan_left"]

        designed_scenes = []
        for idx, s in enumerate(scenes):
            s_num = s.get("scene_number", idx + 1)
            narration = s.get("narration", "")
            concept = s.get("concept_summary", narration[:120])

            # Dynamically infer character, setting, action, and motion from scene context
            char, setting, visual_action, facial_motion = self._infer_scene_elements(
                narration=narration,
                concept=concept,
                custom_char=custom_character,
                custom_env=custom_environment
            )

            # If Groq provided bespoke visual action or facial motion, prioritize and sanitize it!
            groq_action = s.get("visual_action")
            groq_motion = s.get("facial_motion")

            g_act = groq_action.strip().lstrip(',').strip() if (groq_action and groq_action.strip()) else ""
            if not re.search(r'\b(student|students|teacher|professor|school|classroom)\b', narration, re.IGNORECASE):
                g_act = re.sub(r'\b(highlighting\s+student\s+exploration|student\s+exploration|student|students|classroom|school)\b', '', g_act, flags=re.IGNORECASE).strip().strip(', ')

            cleaned_narr = self._clean_script_text(narration)
            # Ensure the action has concrete story subjects, not just empty camera movement words
            camera_movement_only = any(p in g_act.lower() for p in ["core visual concept", "educational demonstration", "visual concept", "student exploration"]) or len(g_act.split()) < 4

            if not g_act or camera_movement_only:
                action_raw = visual_action
            else:
                action_raw = g_act

            action_clarified = self._disambiguate_and_clarify_visual(action_raw, narration=narration)

            prompt_parts = [action_clarified]
            if custom_character and custom_character.strip():
                prompt_parts.append(f"featuring {custom_character.strip()}")
            if custom_environment and custom_environment.strip():
                prompt_parts.append(f"set in {custom_environment.strip()}")
            prompt_parts.append(style["aesthetic"])
            if custom_design_prompt and custom_design_prompt.strip():
                prompt_parts.append(custom_design_prompt.strip())
            prompt_parts.append(style["render_suffix"])

            if groq_motion and len(groq_motion.strip()) > 3 and "N/A" not in groq_motion:
                facial_motion = groq_motion.strip()

            full_image_prompt = ", ".join(prompt_parts)

            s["image_prompt"] = full_image_prompt
            s["motion_prompt"] = facial_motion
            s["motion_style"] = auto_motions[idx % len(auto_motions)]
            s["design_style"] = style_id

            designed_scenes.append(s)

        return designed_scenes

    def _disambiguate_and_clarify_visual(self, visual_prompt: str, narration: str = "") -> str:
        """
        Enhances visual prompts for Disney Pixar aesthetics and eliminates diffusion model hallucinations:
        1. Jackal -> Cute, charming Disney Pixar red fox with bushy tail & pointed ears (prevents headless deer deformities).
        2. Vada -> Crispy golden-brown savory doughnut fritter with center hole (prevents mango/fruit confusion).
        3. Grandmother -> Consistent Disney Pixar elderly grandmother character (Dadi with silver bun & spectacles) ONLY in kitchen/village scenes.
        4. Crow -> Charming Disney Pixar black crow with glossy feathers and curious eyes.
        5. Tree Height -> Extreme low-angle vertical scale showing the ground far below.
        6. Strips toxic negative words (e.g. 'no morphed heads', 'no chimera') that confuse FLUX.
        """
        s = visual_prompt.strip()

        # 0. Universal Diffusion Composition: Diffusion models generate ONE single cohesive still frame.
        # Normalize multi-cut film directions (which cause collage, split-screen, or floating inset heads) into a unified composition.
        s = re.sub(r'\b(shot[- ]reverse[- ]shot|cut to|split[- ]screen|two shots?|multiple angles?)\b', 'cohesive unified shot', s, flags=re.IGNORECASE)
        s = re.sub(r'\b(in the corner of the (frame|image)|in the corner)\b', 'in the background', s, flags=re.IGNORECASE)

        # 1. Cultural food disambiguation: Vada -> physical doughnut fritter description
        if "golden-brown crispy savory fried doughnut fritter" not in s.lower():
            vada_regex = r'\b(a\s+)?(golden\s+)?(round\s+)?(vada|vadai|vadas|medu\s+vada)\b'
            vada_desc = "a round golden-brown crispy savory fried doughnut fritter with a center hole (medu vada snack, savory pastry, not fruit)"
            s = re.sub(vada_regex, vada_desc, s, flags=re.IGNORECASE)

        # 2. Universal Human & Animal Anatomical Grounding:
        combined_text = f"{s} {narration}".lower()

        # Check for Mother & Baby / Parent-Child Multi-Character Pair
        is_parent_child = bool(re.search(r'\b(mother|mom|parent|caregiver|family)\b', combined_text, re.IGNORECASE)) and bool(re.search(r'\b(baby|infant|toddler|child)\b', combined_text, re.IGNORECASE))
        if is_parent_child:
            if not any(k in s.lower() for k in ["both characters", "mother and baby clearly visible", "two-character"]):
                s = f"two-character medium shot featuring BOTH the loving mother and her adorable baby clearly visible together in the frame, mother warmly interacting with the baby, {s}"
        else:
            has_human = bool(re.search(r'\b(man|woman|elderly|person|grandmother|grandpa|grandfather|child|boy|girl|king|queen|knight|prince|princess|chef|farmer|villager|dadi|character|astronaut|explorer|scientist|doctor|warrior|hero|she|he|her|his)\b', combined_text, re.IGNORECASE))
            if has_human and not any(k in s.lower() for k in ["medium shot", "character portrait", "full body", "connected head", "two-character"]):
                s = f"medium shot character portrait, complete visible upper body with natural connected head, neck and torso, {s}"

        # 2B. Material Grounding (Ensures required lesson materials are visibly present):
        if "swing" in combined_text and not any(k in s.lower() for k in ["fabric swing", "infant swing", "cradle swing"]):
            s += ", the baby is safely seated in a cozy fabric infant swing, gently supported by the mother's loving hands"
        if "strawberry" in combined_text and "strawberry" not in s.lower():
            s += ", the mother is holding a fresh bright red ripe strawberry for the baby to observe and smell"
        if "mirror" in combined_text and not any(k in s.lower() for k in ["baby mirror", "floor mirror", "child-size mirror", "mirror"]):
            s += ", the mother is holding a round child-safe baby mirror reflecting both smiling faces"

        # 2C. Environmental Color-Bleed Prevention (Eliminates green skin and green studios):
        if "mint" in s.lower() or "green" in s.lower():
            s = re.sub(r'\b(in the )?(mint[- ]green studio|green studio)\b', 'in the bright modern educational studio with warm neutral cream lighting and RBIQ logo wall', s, flags=re.IGNORECASE)
            s = re.sub(r'\b(mint[- ]green background|green background)\b', 'neutral warm cream and wood studio background with RBIQ logo wall', s, flags=re.IGNORECASE)
            if "maya" in s.lower() and "warm radiant" not in s.lower():
                s += ", Maya has natural warm radiant human skin tone and healthy authentic facial complexion (never green skin)"

        has_animal = bool(re.search(r'\b(fox|jackal|crow|bird|lion|tiger|bear|wolf|dog|puppy|cat|rabbit|deer|monkey|elephant|eagle|owl|sparrow|falcon|crocodile|dragon|dinosaur|snake|horse)\b', combined_text, re.IGNORECASE))
        if has_animal and not any(k in s.lower() for k in ["connected head", "cohesive animal", "complete animal", "avian anatomy", "connected body", "natural connected"]):
            s = f"cohesive single shot with complete natural animal anatomy, {s}"

        # 3. Character Model Consistency: Fox / Jackal in Disney Pixar style
        # FLUX produces deformed deer when prompted with 'golden jackal'. Re-anchoring to cute Pixar fox guarantees adorable results.
        if "charming disney pixar red fox" not in s.lower():
            fox_regex = r'\b(a\s+)?(golden\s+)?(jackal|jackals|sly\s+jackal|clever\s+jackal|fox)\b'
            fox_desc = "medium shot of a clever charming Disney Pixar red fox character with cute pointed ears, warm amber eyes, and a fluffy bushy tail, complete cohesive animal anatomy with natural connected head and body"
            s = re.sub(fox_regex, fox_desc, s, flags=re.IGNORECASE)

        # 3. Character Model Consistency: Crow in Disney Pixar style
        if "charming stylized disney pixar black crow" not in s.lower():
            crow_regex = r'\b(a\s+)?(black\s+crow|crow|curious\s+crow|shiny\s+crow)\b'
            crow_desc = "medium shot of a charming stylized Disney Pixar black crow character with glossy feathers, big expressive eyes, and dark beak, complete cohesive bird anatomy with natural connected head and wings"
            s = re.sub(crow_regex, crow_desc, s, flags=re.IGNORECASE)

        # 4. Character Model Consistency: Grandmother ONLY when scene is actually about the kitchen / grandmother
        # Explicitly specifies full upper body with connected head, neck and shoulders to eliminate detached/floating heads
        if "adorable disney pixar elderly indian grandmother" not in s.lower():
            grandma_scene = any(w in s.lower() for w in ["grandmother", "grandma", "paati", "elderly woman", "kitchen", "cooking stove", "clay stove", "frying"])
            if grandma_scene:
                grandma_anchor = "medium shot character portrait of an adorable Disney Pixar elderly Indian grandmother character named Dadi, complete visible upper body with natural connected head, neck and shoulders, silver hair in a neat bun, round kind expressive eyes, wearing a traditional yellow and red cotton saree, standing cheerfully beside her rustic open-air clay stove"
                s = re.sub(r'\b(an?\s+)?(elderly grandmother|grandmother|grandma|paati|elderly woman)(\s+(character\s+)?named\s+dadi)?\b', grandma_anchor, s, flags=re.IGNORECASE)
                if "dadi" not in s.lower() and ("stove" in s.lower() or "kitchen" in s.lower()):
                    s = f"{grandma_anchor}, {s}"

        # 5. Tree Height & Elevation (when crow is perched high)
        if re.search(r'\b(branch|tree|perched)\b', s, re.IGNORECASE) and "fox" not in s.lower():
            if not any(w in s.lower() for w in ["towering", "elevation", "far below", "vertical scale"]):
                s += ", towering tall tree canopy with the forest floor far below, dramatic vertical scale"

        # 6. Remove rogue student / teacher / classroom words if not in narration
        if not re.search(r'\b(student|students|teacher|professor|school|classroom)\b', narration, re.IGNORECASE):
            s = re.sub(r'\b(highlighting\s+student\s+exploration|student\s+exploration|student|students|classroom|school)\b', '', s, flags=re.IGNORECASE)

        # 7. Remove toxic negative words that confuse FLUX
        toxic_negatives = [
            r'no animal hybrid', r'no hybrid animal', r'no chimera',
            r'no morphed heads or bodies', r'no morphed heads', r'no morphed limbs',
            r'distinct separate character anatomy', r'distinct character anatomy',
            r'distinct separate animals in distinct positions, realistic anatomy'
        ]
        for tn in toxic_negatives:
            s = re.sub(tn, '', s, flags=re.IGNORECASE)

        s = re.sub(r'\s*,\s*', ', ', s)
        s = re.sub(r',\s*,+', ', ', s)
        return s.strip(', ')

    def _clean_script_text(self, text: str) -> str:
        """Removes LMS, pedagogical guide headers, and formatting artifacts."""
        cleaned = re.sub(r'(?i)(Parent/LMS guide|LMS guide|Teacher guide|Guide|Targeted development|Safety|Step \d+)[:\-]', '', text)
        cleaned = re.sub(r'\[.*?\]|\(.*?\)', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _infer_scene_elements(
        self,
        narration: str,
        concept: str,
        custom_char: Optional[str] = None,
        custom_env: Optional[str] = None
    ) -> tuple[str, str, str, str]:
        """
        Analyzes the scene's content to determine:
          1. Character (e.g. mother and baby, pirate, chef, scientist, cute puppy)
          2. Environment setting (e.g. cozy nursery with floor mirror, island beach, kitchen, lab)
          3. Visual action (what is physically happening in the 16:9 frame)
          4. Facial motion prompt (natural blinking, expressions, smile, gestures)
        """
        combined = f"{concept} {narration}".lower()
        cleaned_text = self._clean_script_text(concept if len(concept) > 20 else narration)

        # 1. Baby / Infant / Toddler / Sensory Play
        if any(k in combined for k in ["baby", "infant", "toddler", "mirror play", "baby mirror", "caregiver", "sensory", "nursery", "parent"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Loving caring mother and an adorable happy 8-month-old baby with two large bright expressive eyes, a cute button nose, rosy cheeks, and a joyful smile, perfect facial symmetry, complete well-formed human anatomy"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "warm sunlit cozy nursery playroom, soft pastel playmat, baby-safe floor mirror reflecting the baby"
            )
            action = "the happy baby looking curiously into the floor mirror at their reflection, smiling and clapping small hands delightedly with mother"
            motion = (
                "Baby smiling delightfully with open-mouthed joy, natural eye blinking, gentle curious head tilting, "
                "clapping small hands, mother smiling warmly with affectionate eye contact"
            )
            return char, setting, action, motion

        # 2. Puppy / Dog / Pets / Wildlife / Animals
        if any(k in combined for k in ["puppy", "dog", "bark", "barking", "kitten", "cat", "pet", "animal", "lion", "bear", "bird", "rabbit"]):
            animal_name = "golden retriever puppy"
            for a in ["puppy", "dog", "kitten", "cat", "rabbit", "bear", "lion", "elephant", "bird", "fox"]:
                if a in combined:
                    animal_name = a
                    break
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                f"Cute fluffy {animal_name} with shiny expressive dark eyes and friendly energetic posture"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "vibrant sunny green park with blooming wildflowers, soft golden morning light and lush grass"
            )
            action = f"the playful {animal_name} trotting forward happily, tilting its head with lively curious expression"
            motion = "Playful head tilt, shiny blinking eyes, cheerful open-mouth panting or barking motion, lively energetic movement"
            return char, setting, action, motion

        # 3. Pirate / Treasure Island / Adventure
        if any(k in combined for k in ["pirate", "treasure", "ship", "ocean", "island", "sea", "captain", "sword"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Charismatic expressive pirate with weathered tricorn hat, rustic adventurer coat, and deeply emotive eyes"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "windswept tropical treasure island beach with turquoise waves, palm trees, and an open rustic wooden chest on white sand"
            )
            action = "the pirate kneeling beside an ancient glowing treasure chest, showing heartfelt emotion and wonder"
            motion = "Deeply expressive emotive facial animation, natural eye blinking, subtle head movement, authentic gesturing"
            return char, setting, action, motion

        # 4. Cooking / Baking / Kitchen / Chef
        if any(k in combined for k in ["cook", "chef", "recipe", "kitchen", "baking", "bake", "cake", "food", "dish", "meal", "ingredient"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Cheerful passionate chef in crisp white chef jacket and apron with friendly warm smile"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "bright modern rustic kitchen with warm wooden shelves, marble countertop, and fresh colorful ingredients"
            )
            action = "the chef demonstrating culinary preparation with fresh ingredients and welcoming enthusiasm"
            motion = "Warm welcoming smile, direct eye contact with camera, expressive nodding, natural eye blinking, engaging hand gestures"
            return char, setting, action, motion

        # 5. Space / Astronomy / Planet / Gravity / Universe
        if any(k in combined for k in ["space", "planet", "orbit", "solar", "star", "galaxy", "gravity", "universe", "astronaut", "cosmos"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Curious enthusiastic astronomer in modern explorer jumpsuit with expressive bright eyes"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "futuristic astronomy observatory planetarium with floating luminous 3D planetary orbits and nebula projections"
            )
            action = "exploring floating luminous planetary models and gravitational cosmic orbits"
            motion = "Awe-inspired wide smile, expressive blinking eyes, enthusiastic pointing and engaging presentation gestures"
            return char, setting, action, motion

        # 6. Biology / Cells / DNA / Plants / Photosynthesis
        if any(k in combined for k in ["plant", "photosynthesis", "leaf", "chloroplast", "cell", "dna", "microscope", "biology", "molecule"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Curious nature researcher in casual field jacket with warm friendly demeanor and magnifying glass"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "glowing botanical greenhouse laboratory surrounded by vibrant living plant leaves absorbing golden sunlight"
            )
            action = "observing living plant structures and transparent 3D holographic cellular models"
            motion = "Curious warm smile, engaged eye contact, gentle inquisitive head nod, natural blinking"
            return char, setting, action, motion

        # 7. Science / Physics / Chemistry / Discovery
        if any(k in combined for k in ["science", "scientist", "physics", "chemistry", "experiment", "laboratory", "lab"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Enthusiastic curious scientist in clean modern lab attire with stylish glasses and engaging warm smile"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "high-tech modern science laboratory with glowing interactive holographic diagrams and clean ambient lighting"
            )
            action = "demonstrating an exciting scientific principle with interactive glowing models"
            motion = "Enthusiastic warm smile, direct eye contact with camera, natural eye blinking, lively demonstrative gestures"
            return char, setting, action, motion

        # 8. Doctor / Healthcare / Medicine / Clinic
        if any(k in combined for k in ["doctor", "nurse", "hospital", "clinic", "health", "medicine", "patient"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Compassionate healthcare professional in clean modern scrubs with stethoscope and comforting warm smile"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "contemporary bright wellness clinic with calm natural lighting and soothing decor"
            )
            action = "providing reassuring health and wellness guidance with genuine empathy"
            motion = "Comforting gentle smile, reassuring eye contact, attentive nodding, natural blinking"
            return char, setting, action, motion

        # 9. Teacher / Educator (ONLY if explicitly mentioned in user prompt or character request!)
        if any(k in combined for k in ["teacher", "professor", "instructor", "lecturer"]):
            char = (
                custom_char.strip() if custom_char and custom_char.strip() else
                "Friendly charismatic educator with warm expressive smile and engaging presence"
            )
            setting = (
                custom_env.strip() if custom_env and custom_env.strip() else
                "vibrant modern interactive learning studio with colorful educational visuals and warm ambient lighting"
            )
            action = "presenting the concept with welcoming clarity"
            motion = "Warm friendly smile, direct engaging eye contact, natural blinking, expressive head nods"
            return char, setting, action, motion

        # 10. General / Custom Fallback
        char = (
            custom_char.strip() if custom_char and custom_char.strip() else
            "Expressive friendly character with warm natural facial features and engaging smile"
        )
        setting = (
            custom_env.strip() if custom_env and custom_env.strip() else
            "beautifully lit atmospheric studio setting matching the theme with soft depth of field"
        )
        action_summary = cleaned_text[:80] if cleaned_text else "the main concept"
        action = f"engaging with {action_summary}"
        motion = "Warm friendly smile, direct eye contact with camera, natural eye blinking, gentle nodding motion, lively gestures"
        return char, setting, action, motion

design_agent = DesignAgent()
