"""LLM-based Semantic Analyzer for KubeJS scripts."""

import json
import logging
import re
from typing import Dict

from openai import OpenAI

from modpack_localization_auto.config import AppConfig

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a KubeJS semantic analysis expert. You will be provided with KubeJS scripts (JavaScript).
Your task is to comprehensively analyze the code, specifically targeting `event.create(...)` calls that use template literals (e.g. `${name}`) inside loops, arrays, or functions.
You must mentally execute the script and enumerate all the exact, concrete ID strings that would be generated at runtime, along with their corresponding English `.displayName(...)` values.

Return ONLY a valid JSON object mapping the generated `id` to its `display_name`.
If no dynamic items are generated, return an empty JSON object: {}

Example Input:
```javascript
let mechanism = (name) => {
  let id = name.toLowerCase();
  event.create(`incomplete_${id}_mechanism`).displayName(`Incomplete ${name} Mechanism`);
};
mechanism("Copper");
mechanism("Steel");
```

Example Output:
```json
{
  "incomplete_copper_mechanism": "Incomplete Copper Mechanism",
  "incomplete_steel_mechanism": "Incomplete Steel Mechanism"
}
```

CRITICAL RULES:
1. Do not include markdown code block syntax (like ```json) in your final response. Return pure JSON.
2. Only include entries that are dynamically generated with template variables in the provided code.
3. If an ID or name cannot be confidently determined or depends on external data not present in the code, do your absolute best to infer it, or skip it if impossible.
4. IMPORTANT FILTERING: DO NOT extract garbage or debug values. If the generated name is just a 3-4 letter meaningless capitalized acronym (e.g. "ABE", "ACA", "ACD", "AML") or simple numbers, DO NOT include them in the returned JSON. KubeJS authors often do this for internal map variables. We only want legitimate, human-readable item/block/fluid names like "Copper Mechanism" or "Molten Diamond".
"""

def analyze_kubejs_script_for_dynamic_keys(content: str, config: AppConfig) -> Dict[str, str]:
    """
    Use the designated Code LLM to analyze a JS file for dynamic template literal registries.
    Returns a dictionary of permutations (kubejs.item.xxx, kubejs.block.xxx) mapping to their names.
    """
    if not config.code_llm_api_key or not config.code_llm_model_id:
        logger.warning("Code LLM is not configured. Skipping JS Semantic Analysis.")
        return {}

    logger.info("Triggering LLM Semantic Analyzer for KubeJS script...")
    
    client = OpenAI(
        base_url=config.code_llm_base_url if config.code_llm_base_url else None,
        api_key=config.code_llm_api_key,
    )
    
    try:
        response = client.chat.completions.create(
            model=config.code_llm_model_id,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0.1,  # We want highly deterministic code analysis
            timeout=120.0,
        )
        
        reply = response.choices[0].message.content or "{}"
        
        # Clean up potential markdown formatting natively as a fallback
        reply = reply.strip()
        if reply.startswith("```json"):
            reply = reply[7:]
        if reply.startswith("```"):
            reply = reply[3:]
        if reply.endswith("```"):
            reply = reply[:-3]
            
        inferred_map: dict[str, str] = json.loads(reply.strip())
        
        # Now, expand these IDs into the definitive KubeJS localization permutation formats
        # Since KubeJS registers an item, block, fluid, and bucket for every single create() call under the hood,
        # we generate all formats as translations to be safe.
        final_permutations: dict[str, str] = {}
        for item_id, eng_name in inferred_map.items():
            final_permutations[f"item.kubejs.{item_id}"] = eng_name
            final_permutations[f"block.kubejs.{item_id}"] = eng_name
            final_permutations[f"fluid.kubejs.{item_id}"] = eng_name
            
            # Fluid buckets: _bucket
            final_permutations[f"item.kubejs.{item_id}_bucket"] = f"{eng_name} Bucket"
            
        if final_permutations:
            logger.info("LLM gracefully extracted %d dynamic keys!", len(final_permutations))
            
        return final_permutations
        
    except Exception as e:
        logger.error("LLM Analyzer failed on script: %s", e)
        return {}
