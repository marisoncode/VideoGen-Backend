import os
import re
import json
import requests
from typing import List, Dict, Any, Optional
from app.services.document_service import document_service
from app.core.config import settings

class ScriptAgent:
    """
    Dedicated Script & Storyboard Agent:
    Transforms any raw input (PDF syllabus, Word docs, Excel/CSV sheets,
    live Google Docs & Sheets links, lecture notes, pre-written script, or idea prompt)
    into structured, engaging video scenes.
    Powered by Groq's high-speed LLM (openai/gpt-oss-120b) with automatic fallback
    to deterministic NLP text chunking.
    """

    GROQ_PRIMARY_MODEL = "openai/gpt-oss-120b"
    GROQ_FALLBACK_MODEL = "qwen/qwen3.8-27b"

    def process_input(
        self,
        input_mode: str,
        topic_prompt: Optional[str] = None,
        script_text: Optional[str] = None,
        file_bytes: Optional[bytes] = None,
        filename: Optional[str] = None,
        live_url: Optional[str] = None,
        chapter_topic: Optional[str] = None,
        target_audience: Optional[str] = None,
        target_duration: int = 120
    ) -> Dict[str, Any]:
        """
        Processes any raw input source into a list of structured scenes with titles, narrations,
        and educational concepts.
        Calibrates pacing for 2 to 5 minute videos (120s - 300s) and filters multi-page textbook content.
        """
        target_duration = max(15, min(600, int(target_duration or 120)))
        title = "Educational Explainer"
        raw_text = ""
        audience_label = (target_audience or "Middle School (Grade 6-8)").strip()

        # 1. Live Google Docs & Sheets URL
        if (input_mode == "google_url" or (live_url and live_url.strip())) and live_url:
            clean_url = live_url.strip()
            if "spreadsheets/d" in clean_url:
                title = "Live Google Sheet Presentation"
                raw_text = document_service.fetch_live_google_sheet(clean_url)
            elif "document/d" in clean_url:
                title = "Live Google Doc Explainer"
                raw_text = document_service.fetch_live_google_doc(clean_url)
            else:
                try:
                    r = requests.get(clean_url, timeout=15)
                    raw_text = re.sub(r'<[^>]+>', ' ', r.text)
                    title = "Web Document Presentation"
                except Exception as e:
                    raise ValueError(f"Could not fetch document from URL: {e}")

            raw_text = document_service.clean_text(raw_text)

        # 2. Uploaded Document / Spreadsheet File (Textbook PDF)
        elif input_mode == "document" and file_bytes:
            safe_fn = filename or "textbook.pdf"
            base_name = safe_fn.rsplit(".", 1)[0].replace("_", " ").title()
            title = f"{chapter_topic.title()} - {base_name}" if chapter_topic else base_name
            full_extracted = document_service.parse_uploaded_file(file_bytes, safe_fn)
            # Filter to relevant chapter/topic without discarding important content
            raw_text = document_service.extract_topic_section(
                full_text=full_extracted,
                chapter_topic=chapter_topic or topic_prompt,
                max_chars=12000
            )

        # 3. Pasted Script
        elif input_mode == "script" and script_text and script_text.strip():
            title = "Textbook Lesson Explainer"
            raw_text = document_service.clean_text(script_text)

        # 4. Prompt / Topic mode
        else:
            topic = (topic_prompt or "Photosynthesis and Plant Biology").strip()
            title = f"{topic.title()} Explainer"
            raw_text = topic

        # Call Groq High-Speed LLM Screenwriter
        content_for_llm = raw_text if len(raw_text) > 15 else (topic_prompt or title)
        groq_result = self._call_groq_storyboard(
            text=content_for_llm,
            default_topic=title,
            target_duration=target_duration,
            target_audience=audience_label,
            chapter_topic=chapter_topic
        )

        if groq_result and groq_result.get("scenes"):
            min_scenes, _ = self._calculate_scene_bounds(target_duration)
            scenes = self._enforce_scene_pacing(
                scenes=groq_result["scenes"],
                min_scenes=min_scenes,
                target_duration=target_duration
            )
            total_est = 0
            for s in scenes:
                narration_text = s.get("narration", "")
                wc = len(narration_text.split())
                calc_dur = max(8, round(wc / 2.3))
                s["estimated_duration"] = s.get("estimated_duration") or calc_dur
                total_est += s["estimated_duration"]

            return {
                "title": groq_result.get("title", title),
                "introduction": groq_result.get("introduction", ""),
                "target_duration": target_duration,
                "target_audience": audience_label,
                "estimated_total_duration": total_est,
                "scenes": scenes,
                "raw_text_length": len(raw_text),
                "engine": "groq_llm"
            }

        # If user explicitly provided a pre-written multi-scene script with scene markers, allow parsing their actual words
        if input_mode == "script" and raw_text.strip() and len(raw_text.strip()) > 30:
            print(f"[ScriptAgent] Parsing user-provided script content into timed scenes (target: {target_duration}s)...")
            scenes = self._segment_text_into_scenes(raw_text, default_topic=title, target_duration=target_duration)
            total_est = sum(s.get("estimated_duration", max(5, round(len(s.get("narration", "").split()) / 2.3))) for s in scenes)
            return {
                "title": title,
                "introduction": "",
                "target_duration": target_duration,
                "target_audience": audience_label,
                "estimated_total_duration": total_est,
                "scenes": scenes,
                "raw_text_length": len(raw_text),
                "engine": "user_script_parser"
            }

        # No dummy fallback allowed - raise error
        raise ValueError("Script generation failed: Groq LLM did not return a valid storyboard. Please check your prompt and GROQ_API_KEY.")

    def _calculate_scene_bounds(self, target_duration: int) -> tuple[int, int]:
        """
        Calculates optimal minimum and maximum scene counts for dynamic educational video pacing.
        Each visual keyframe lasts approx 13 to 17 seconds to keep viewers visually engaged.
        For a 120s (2m) video, yields 7 to 9 scenes (~15s per scene).
        """
        if target_duration <= 35:
            return 2, 3
        elif target_duration <= 75:   # ~1 minute (60s) -> 4 to 6 scenes (~12-15s per scene)
            return 4, 6
        elif target_duration <= 135:  # ~2 minutes (120s) -> 7 to 9 scenes (~13-17s per scene)
            return 7, 9
        elif target_duration <= 195:  # ~3 minutes (180s) -> 10 to 12 scenes (~15-18s per scene)
            return 10, 12
        elif target_duration <= 255:  # ~4 minutes (240s) -> 13 to 15 scenes
            return 13, 15
        else:                         # 5 minutes (300s) -> 16 to 20 scenes
            return 16, 20

    def _enforce_scene_pacing(
        self,
        scenes: List[Dict[str, Any]],
        min_scenes: int,
        target_duration: int
    ) -> List[Dict[str, Any]]:
        """
        Guarantees that a video has at least min_scenes so visuals transition every 13-17 seconds.
        If an LLM returned fewer scenes than required, splits multi-sentence scenes with diverse visual angles
        while preserving concrete story subject matter and eliminating non-story hallucinations.
        """
        if not scenes:
            return scenes

        if len(scenes) >= min_scenes:
            for idx, s in enumerate(scenes):
                s["scene_number"] = idx + 1
            return scenes

        camera_angles = [
            "wide cinematic establishing shot with atmospheric lighting",
            "medium close-up character shot with sharp focal depth",
            "high-angle perspective capturing the environment",
            "side profile angle with warm cinematic illumination",
            "dynamic eye-level framing with cinematic depth of field",
            "crisp focused framing capturing the character action"
        ]

        print(f"[ScriptAgent] Pacing check: LLM returned {len(scenes)} scenes for {target_duration}s. Expanding to {min_scenes} visual beats...")
        expanded = list(scenes)

        iterations = 0
        while len(expanded) < min_scenes and iterations < 15:
            iterations += 1
            longest_idx = max(range(len(expanded)), key=lambda i: len(expanded[i].get("narration", "").split()))
            target_scene = expanded[longest_idx]
            narration = target_scene.get("narration", "").strip()
            sentences = [sent.strip() for sent in re.split(r'(?<=[.!?])\s+', narration) if sent.strip()]

            if len(sentences) >= 2:
                mid = len(sentences) // 2
                part1_text = " ".join(sentences[:mid])
                part2_text = " ".join(sentences[mid:])

                base_title = re.sub(r'(\s*\((Overview|Demonstration|In Detail|Close-up|Part \d+)\))+', '', target_scene.get('title', 'Concept'), flags=re.IGNORECASE).strip()
                raw_vis = target_scene.get('visual_action', '').strip()
                clean_vis = re.sub(r',?\s*(wide establishing|medium close-up|engaging overhead|side profile|dynamic perspective|crisp focused).*$', '', raw_vis, flags=re.IGNORECASE).strip().lstrip(',').strip()

                angle_idx_1 = (len(expanded) * 2) % len(camera_angles)
                angle_idx_2 = (len(expanded) * 2 + 1) % len(camera_angles)

                # Prioritize concrete story action from each part's narration so every scene has distinct, relevant subjects
                action1 = part1_text.strip().rstrip('.') if (len(clean_vis) < 15 or "core visual concept" in clean_vis.lower()) else f"{clean_vis} (focused on {part1_text[:60].strip()})"
                action2 = part2_text.strip().rstrip('.') if (len(clean_vis) < 15 or "core visual concept" in clean_vis.lower()) else f"{clean_vis} (focused on {part2_text[:60].strip()})"

                s1 = dict(target_scene)
                s1["title"] = f"{base_title} (Part 1)"
                s1["narration"] = part1_text
                s1["subtitle"] = sentences[0][:130]
                s1["visual_action"] = f"{action1}, {camera_angles[angle_idx_1]}"

                s2 = dict(target_scene)
                s2["title"] = f"{base_title} (Part 2)"
                s2["narration"] = part2_text
                s2["subtitle"] = sentences[mid][:130] if mid < len(sentences) else part2_text[:130]
                s2["visual_action"] = f"{action2}, {camera_angles[angle_idx_2]}"

                expanded = expanded[:longest_idx] + [s1, s2] + expanded[longest_idx + 1:]
            else:
                # If only 1 long sentence exists, split by commas or coordinating conjunctions
                clauses = [c.strip() for c in re.split(r'[,;]|\s+(?:and|while|as|then|but)\s+', narration) if len(c.strip().split()) >= 3]
                if len(clauses) >= 2:
                    mid = len(clauses) // 2
                    part1_text = ", ".join(clauses[:mid]) + "."
                    part2_text = ", ".join(clauses[mid:]) + "."

                    base_title = re.sub(r'(\s*\((Overview|Demonstration|In Detail|Close-up|Part \d+)\))+', '', target_scene.get('title', 'Concept'), flags=re.IGNORECASE).strip()
                    raw_vis = target_scene.get('visual_action', '').strip()
                    clean_vis = re.sub(r',?\s*(wide establishing|medium close-up|engaging overhead|side profile|dynamic perspective|crisp focused).*$', '', raw_vis, flags=re.IGNORECASE).strip().lstrip(',').strip()

                    angle_idx_1 = (len(expanded) * 2) % len(camera_angles)
                    angle_idx_2 = (len(expanded) * 2 + 1) % len(camera_angles)

                    action1 = part1_text.strip().rstrip('.') if (len(clean_vis) < 15 or "core visual concept" in clean_vis.lower()) else f"{clean_vis} (focused on {part1_text[:60].strip()})"
                    action2 = part2_text.strip().rstrip('.') if (len(clean_vis) < 15 or "core visual concept" in clean_vis.lower()) else f"{clean_vis} (focused on {part2_text[:60].strip()})"

                    s1 = dict(target_scene)
                    s1["title"] = f"{base_title} (Part 1)"
                    s1["narration"] = part1_text
                    s1["subtitle"] = clauses[0][:130]
                    s1["visual_action"] = f"{action1}, {camera_angles[angle_idx_1]}"

                    s2 = dict(target_scene)
                    s2["title"] = f"{base_title} (Part 2)"
                    s2["narration"] = part2_text
                    s2["subtitle"] = clauses[mid][:130] if mid < len(clauses) else part2_text[:130]
                    s2["visual_action"] = f"{action2}, {camera_angles[angle_idx_2]}"

                    expanded = expanded[:longest_idx] + [s1, s2] + expanded[longest_idx + 1:]
                else:
                    break

        for idx, s in enumerate(expanded):
            s["scene_number"] = idx + 1
            wc = len(s.get("narration", "").split())
            s["estimated_duration"] = max(8, round(wc / 2.3))

        return expanded

    def _call_groq_storyboard(
        self,
        text: str,
        default_topic: str,
        target_duration: int = 120,
        target_audience: str = "Middle School (Grade 6-8)",
        chapter_topic: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Calls Groq API to screenwrite an educational video storyboard specifically calibrated
        to the user's requested target_duration (e.g. 2, 3, 4, 5 mins) and school grade.
        Enforces strict JSON schema, educational fidelity, and robust scene pacing.
        """
        api_key = os.getenv("GROQ_API_KEY", "").strip() or getattr(settings, "GROQ_API_KEY", "").strip()
        if not api_key or not api_key.startswith("gsk_"):
            raise ValueError("GROQ_API_KEY is missing or invalid. Please configure your Groq API key in backend/.env to screenwrite scripts.")

        total_target_words = int(target_duration * 2.3)
        min_scenes, max_scenes = self._calculate_scene_bounds(target_duration)
        avg_scenes = (min_scenes + max_scenes) / 2
        avg_scene_dur = max(10, round(target_duration / avg_scenes))
        words_per_scene = max(25, round(total_target_words / avg_scenes))

        topic_instruction = f"Focus strictly on explaining: '{chapter_topic}'." if chapter_topic else "Explain the core educational concepts thoroughly."

        prompt = f"""You are a master educational curriculum director and video screenwriter for school students.
Transform the following textbook content into an engaging, factual educational video storyboard.

MANDATORY PEDAGOGICAL SPECIFICATIONS:
- TARGET TOTAL VIDEO DURATION: {target_duration} seconds ({target_duration // 60}m {target_duration % 60}s).
- MANDATORY SCENE COUNT: The 'scenes' array MUST contain between {min_scenes} and {max_scenes} distinct scenes!
  * For a {target_duration}s video, writing fewer than {min_scenes} scenes is strictly forbidden. You must write at least {min_scenes} scenes (e.g. {min_scenes} to {max_scenes} scenes).
  * Every 13-16 seconds MUST transition to a new visual scene with a distinct camera angle to keep viewers visually engaged.
- SCRIPT LENGTH & WORD COUNT: Speech rate is 2.3 words/second.
  * TOTAL narration across all scenes combined must equal approximately {total_target_words} words.
  * Each scene's narration must have approximately {words_per_scene} words (3-5 comprehensive, age-appropriate sentences). Do NOT write brief 1-sentence summaries!
- TARGET AUDIENCE / GRADE: {target_audience}.
- {topic_instruction}
- STRICT FACTUAL INTEGRITY: Preserve textbook facts and definitions accurately. Never fabricate unsupported claims.
- VISUAL ACTION & CINEMATOGRAPHY RULES:
  * CHARACTER CAST INTEGRITY: When a story introduces key characters (e.g. an elderly grandmother making food, a crow, a jackal), the opening scenes MUST visibly feature those characters. Frame human characters in a medium shot showing their full upper body, shoulders, and connected posture (e.g. kind elderly grandmother standing cheerfully beside her rustic clay stove frying food), never an extreme macro close-up of cookware that causes floating heads or detached body parts!
  * NO ANIMAL CHIMERAS / HYBRIDS: AI image generators easily blend features if two different animals are described in the same close-up (e.g. creating a crow with a jackal head or body). To prevent this, prefer shot-reverse-shot cinematography:
    - Dedicated Scene A: Focus solely on the golden jackal on the forest floor looking upward.
    - Dedicated Scene B: Focus solely on the black crow perched high on the branch looking down.
    - If both appear in one wide shot, explicitly isolate them: "On the ground below stands a golden jackal looking up; high above in the top branches of a towering 35-foot tree perches a separate black crow. Distinct separate creatures."
  * CONCRETE DESCRIPTIONS FOR CULTURAL FOOD & PROPS: The AI image generator does NOT recognize regional words like 'vada' alone and will draw a mango or random fruit! Always describe cultural food physically: "a round golden-brown crispy savory fried doughnut fritter with a hole in the center (medu vada snack, savory fried pastry, distinct from any fruit or mango)".
  * TREE HEIGHT & SCALE: Always convey vertical scale when an animal is in a tree: "extreme low-angle shot looking up at a towering 35-foot tall tree with the forest ground far below" so the tree looks impressively tall.
- CRITICAL: NO text, lettering, or watermarks inside image visual action. Labels and subtitles will be burned during video assembly.
- NO UNWANTED TEACHERS/STUDENTS/CLASSROOMS: Do NOT introduce human students, teachers, presenters, or classrooms unless the user explicitly requested them in the prompt. For stories, fables, animals, and nature narratives, visually portray ONLY the actual characters, animals, and physical environments of the story!
- SAFETY: Visual descriptions must be wholesome, family-friendly, and educational. Avoid physical contact words or resting on beds/mats to prevent cloud image safety filter false-positives.

Output JSON strictly adhering to this schema (You MUST generate at least {min_scenes} sequential scenes in the 'scenes' list):
{{
  "title": "Engaging Lesson Title",
  "introduction": "1-2 sentence hook introducing the topic to students",
  "target_duration": {target_duration},
  "estimated_total_duration": {target_duration},
  "target_audience": "{target_audience}",
  "scenes": [
    {{
      "scene_number": 1,
      "title": "Scene 1: Introduction & Discovery",
      "narration": "First spoken explanation (~{words_per_scene} words).",
      "subtitle": "On-screen subtitle caption under 130 characters",
      "concept_summary": "Core concept introduced",
      "source_reference": "Page/chapter reference if available",
      "estimated_duration": {avg_scene_dur},
      "visual_action": "Photorealistic 16:9 cinematic educational visual action, clean without any text",
      "facial_motion": "Expressive character emotion, warm smile, natural eye blinking"
    }},
    {{
      "scene_number": 2,
      "title": "Scene 2: Core Concept Breakdown",
      "narration": "Detailed explanation for scene 2 (~{words_per_scene} words).",
      "subtitle": "On-screen subtitle caption under 130 characters",
      "concept_summary": "First mechanism or experiment step",
      "source_reference": "Page/chapter reference if available",
      "estimated_duration": {avg_scene_dur},
      "visual_action": "Detailed close-up laboratory or demonstration visual, clean without any text",
      "facial_motion": "Intrigued expression, pointing to demonstration"
    }},
    {{
      "scene_number": 3,
      "title": "Scene 3: Mechanism in Action",
      "narration": "Detailed explanation for scene 3 (~{words_per_scene} words).",
      "subtitle": "On-screen subtitle caption under 130 characters",
      "concept_summary": "Second mechanism or experiment step",
      "source_reference": "Page/chapter reference if available",
      "estimated_duration": {avg_scene_dur},
      "visual_action": "Dynamic 3D model or nature demonstration visual, clean without any text",
      "facial_motion": "Engaged curious expression, lively natural movement"
    }}
  ]
}}

Textbook Source Content:
{text[:10000]}"""

        last_error = ""
        for model in [self.GROQ_PRIMARY_MODEL, self.GROQ_FALLBACK_MODEL]:
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a professional educational video screenwriter. Respond ONLY in valid JSON matching the schema."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.25,
                    "max_tokens": 4096
                }
                res = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=45
                )
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = self._safe_parse_json(content)
                    if parsed and parsed.get("scenes") and len(parsed["scenes"]) > 0:
                        # If model returned fewer than min_scenes, attempt an immediate expansion
                        if len(parsed["scenes"]) < min_scenes:
                            print(f"[ScriptAgent] Groq ({model}) returned {len(parsed['scenes'])} scenes. Requesting full {min_scenes}-scene expansion...")
                            followup_msgs = [
                                {"role": "system", "content": "You are a professional educational video screenwriter. Respond ONLY in valid JSON matching the schema."},
                                {"role": "user", "content": prompt},
                                {"role": "assistant", "content": content},
                                {"role": "user", "content": f"You generated {len(parsed['scenes'])} scenes. A full {target_duration}s ({target_duration//60}m) video requires AT LEAST {min_scenes} distinct scenes (one every 13-16 seconds) with approx {total_target_words} total words. Rewrite and return JSON with {min_scenes} to {max_scenes} comprehensive scenes."}
                            ]
                            try:
                                res2 = requests.post(
                                    "https://api.groq.com/openai/v1/chat/completions",
                                    headers=headers,
                                    json={
                                        "model": model,
                                        "messages": followup_msgs,
                                        "response_format": {"type": "json_object"},
                                        "temperature": 0.3,
                                        "max_tokens": 4096
                                    },
                                    timeout=45
                                )
                                if res2.status_code == 200:
                                    parsed2 = self._safe_parse_json(res2.json()["choices"][0]["message"]["content"])
                                    if parsed2 and parsed2.get("scenes") and len(parsed2["scenes"]) > len(parsed["scenes"]):
                                        parsed = parsed2
                            except Exception as e:
                                print(f"[ScriptAgent] Expansion follow-up notice: {e}")

                        print(f"[ScriptAgent] Successfully generated educational storyboard with Groq ({model}) for {target_duration}s ({len(parsed['scenes'])} scenes)!")
                        return parsed
                elif res.status_code == 401:
                    raise ValueError("Groq API authorization failed (HTTP 401: Invalid API Key). Please verify your GROQ_API_KEY in backend/.env.")
                elif res.status_code == 429:
                    raise ValueError("Groq API rate limit or quota exceeded (HTTP 429: Rate Limit Exceeded). Please wait a moment or check your Groq limits.")
                else:
                    last_error = f"HTTP {res.status_code}: {res.text[:180]}"
                    print(f"[ScriptAgent] Groq notice ({model}): {last_error}")
            except ValueError:
                raise
            except Exception as e:
                last_error = str(e)
                print(f"[ScriptAgent] Groq connection notice ({model}): {e}")

        raise ValueError(f"Groq AI script generation failed: {last_error or 'No response from Groq'}. Please check your GROQ_API_KEY.")

    def _safe_parse_json(self, raw_str: str) -> Optional[Dict[str, Any]]:
        """Robust JSON parser that handles codeblocks and removes markdown formatting."""
        if not raw_str:
            return None
        cleaned = raw_str.strip()
        # Strip markdown fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)
            cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except Exception:
            # Fallback regex search for outer JSON object
            m = re.search(r'(\{[\s\S]*\})', cleaned)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
        return None

    def _segment_text_into_scenes(self, text: str, default_topic: str, target_duration: int = 60) -> List[Dict[str, Any]]:
        """Parses written scripts into structured scenes calibrated to target duration."""
        if not text or not text.strip():
            raise ValueError("No text or script content provided to segment.")

        target_duration = max(15, min(600, target_duration))
        if target_duration <= 35:
            target_scene_count = 2
        elif target_duration <= 75:
            target_scene_count = 3
        elif target_duration <= 110:
            target_scene_count = 4
        elif target_duration <= 160:
            target_scene_count = 6
        else:
            target_scene_count = max(5, min(12, round(target_duration / 20)))

        pattern = r'(?:^|\n)(?:Scene\s*\d+|Act\s*\d+|Part\s*\d+|Chapter\s*\d+)[:\-\s]*'
        markers = list(re.finditer(pattern, text, re.IGNORECASE))

        raw_blocks = []
        if len(markers) >= 2:
            for i in range(len(markers)):
                start = markers[i].end()
                end = markers[i+1].start() if i + 1 < len(markers) else len(text)
                header = markers[i].group(0).strip()
                block_content = text[start:end].strip()
                if block_content:
                    raw_blocks.append((header, block_content))
        else:
            paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
            if not paragraphs:
                sentences = re.split(r'(?<=[.!?])\s+', text)
                chunk = []
                cur_len = 0
                for s in sentences:
                    chunk.append(s)
                    cur_len += len(s)
                    if cur_len > 180:
                        paragraphs.append(" ".join(chunk))
                        chunk = []
                        cur_len = 0
                if chunk:
                    paragraphs.append(" ".join(chunk))

            # Distribute paragraphs into target_scene_count buckets
            if paragraphs:
                bucket_size = max(1, len(paragraphs) // target_scene_count)
                for i in range(target_scene_count):
                    start_p = i * bucket_size
                    if i == target_scene_count - 1:
                        end_p = len(paragraphs)
                    else:
                        end_p = min(len(paragraphs), (i + 1) * bucket_size)
                    subset = paragraphs[start_p:end_p]
                    if subset:
                        raw_blocks.append((f"Scene {i+1}", "\n".join(subset)))

        if not raw_blocks:
            raw_blocks = [("Scene 1", text)]

        scenes = []
        avg_sec = round(target_duration / max(1, len(raw_blocks)))

        for idx, (header, content) in enumerate(raw_blocks):
            s_num = idx + 1
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            title = header

            if len(lines) >= 2 and len(lines[0]) < 60 and not lines[0].endswith("."):
                title = f"{header}: {lines[0]}"
                narration = " ".join(lines[1:])
            else:
                title = f"{header}: Concept {s_num}"
                narration = " ".join(lines)

            clean_narration = re.sub(r'\[.*?\]|\(.*?\)', '', narration).strip()
            if not clean_narration:
                clean_narration = narration

            first_sentence = re.split(r'(?<=[.!?])\s+', clean_narration)[0]
            subtitle = first_sentence if len(first_sentence) < 140 else first_sentence[:137] + "..."
            est_dur = max(5, round(len(clean_narration.split()) / 2.3))

            scenes.append({
                "scene_number": s_num,
                "title": title,
                "narration": clean_narration,
                "subtitle": subtitle,
                "concept_summary": clean_narration[:100],
                "estimated_duration": est_dur
            })

        return scenes

script_agent = ScriptAgent()
