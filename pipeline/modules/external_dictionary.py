#!/usr/bin/env python3
"""
External Dictionary API Integration Module

Provides lookups from external dictionary API:
- KanjiAPI.dev (Unified Japanese-English/Vietnamese dictionary)

Features:
- Automatic caching to avoid rate limits
- EDICT/KANJIDIC dictionary data (13,000+ kanji)
- JLPT level information
- Unified API for both EN and VN translations

Author: MTL Studio
Version: 2.0 (Unified KanjiAPI)
Date: 2026-02-01
"""

import os
import json
import time
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Optional imports
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests not installed. External dictionary APIs disabled.")


class DictionaryCache:
    """
    Simple file-based cache for dictionary lookups.
    
    Stores results in JSON files to avoid repeated API calls.
    """
    
    def __init__(self, cache_dir: str = "cache/dictionary", ttl_hours: int = 168):
        """
        Initialize cache.
        
        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Cache time-to-live in hours (default: 1 week)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        
        # In-memory cache for current session
        self._memory_cache: Dict[str, Any] = {}
    
    def _get_cache_key(self, term: str, source: str) -> str:
        """Generate cache key from term and source."""
        key = f"{source}:{term}"
        return hashlib.md5(key.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{cache_key}.json"
    
    def get(self, term: str, source: str = 'kanjiapi') -> Optional[Dict]:
        """
        Get cached result for term.
        
        Args:
            term: Japanese term to look up
            source: API source (default: kanjiapi)
            
        Returns:
            Cached result or None if not found/expired
        """
        cache_key = self._get_cache_key(term, source)
        
        # Check memory cache first
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]
        
        # Check file cache
        cache_path = self._get_cache_path(cache_key)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                
                # Check TTL
                cached_time = datetime.fromisoformat(cached.get('timestamp', '2000-01-01'))
                if datetime.now() - cached_time < self.ttl:
                    result = cached.get('data')
                    self._memory_cache[cache_key] = result
                    return result
            except Exception as e:
                logger.warning(f"Cache read error for {term}: {e}")
        
        return None
    
    def set(self, term: str, source: str, data: Dict) -> None:
        """
        Cache result for term.
        
        Args:
            term: Japanese term
            source: API source
            data: Result data to cache
        """
        cache_key = self._get_cache_key(term, source)
        
        # Store in memory
        self._memory_cache[cache_key] = data
        
        # Store in file
        cache_path = self._get_cache_path(cache_key)
        try:
            cached = {
                'term': term,
                'source': source,
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cached, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Cache write error for {term}: {e}")


class KanjiAPI:
    """
    KanjiAPI.dev client for unified Japanese lookups.
    
    API: https://kanjiapi.dev/v1/
    Endpoints:
        - /v1/kanji/{character} - Single kanji lookup
        - /v1/reading/{reading} - Lookup by reading
        - /v1/words/{word} - Word lookup
    
    Data sources: EDICT, KANJIDIC dictionaries (13,000+ kanji)
    Features: Meanings, readings, JLPT levels, grades, frequency data
    """
    
    BASE_URL = "https://kanjiapi.dev/v1"
    
    def __init__(self, cache: Optional[DictionaryCache] = None):
        self.cache = cache or DictionaryCache()
        self._last_request = 0
        self._min_interval = 0.5  # More lenient than old APIs
    
    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()
    
    def lookup_kanji(self, character: str) -> Optional[Dict]:
        """
        Look up a single kanji character.
        
        Args:
            character: Single kanji character to look up
            
        Returns:
            Dictionary with kanji data or None if not found
        """
        if not REQUESTS_AVAILABLE or len(character) != 1:
            return None
        
        # Check cache
        cached = self.cache.get(character, 'kanjiapi')
        if cached:
            logger.debug(f"[KANJIAPI] Cache hit: {character}")
            return cached
        
        try:
            self._rate_limit()
            
            response = requests.get(
                f"{self.BASE_URL}/kanji/{character}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                result = self._parse_kanji_response(character, data)
                self.cache.set(character, 'kanjiapi', result)
                logger.debug(f"[KANJIAPI] Found: {character} → {result.get('meanings', [])}")
                return result
            
            logger.debug(f"[KANJIAPI] Not found: {character}")
            return None
            
        except Exception as e:
            logger.warning(f"[KANJIAPI] API error for {character}: {e}")
            return None
    
    def lookup_word(self, word: str) -> Optional[Dict]:
        """
        Look up a Japanese word/compound.
        
        Args:
            word: Japanese word to look up
            
        Returns:
            Dictionary with word data or None if not found
        """
        if not REQUESTS_AVAILABLE:
            return None
        
        # Check cache
        cached = self.cache.get(word, 'kanjiapi')
        if cached:
            logger.debug(f"[KANJIAPI] Cache hit: {word}")
            return cached
        
        try:
            self._rate_limit()
            
            response = requests.get(
                f"{self.BASE_URL}/words/{word}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                result = self._parse_word_response(word, data)
                self.cache.set(word, 'kanjiapi', result)
                logger.debug(f"[KANJIAPI] Found: {word} → {result.get('meanings', [])}")
                return result
            
            logger.debug(f"[KANJIAPI] Not found: {word}")
            return None
            
        except Exception as e:
            logger.warning(f"[KANJIAPI] API error for {word}: {e}")
            return None
    
    def lookup(self, term: str) -> Optional[Dict]:
        """
        Smart lookup - tries word lookup first, falls back to character-by-character.
        
        Args:
            term: Japanese term (word or single kanji)
            
        Returns:
            Lookup result or None if not found
        """
        # Try word lookup first
        if len(term) > 1:
            result = self.lookup_word(term)
            if result:
                return result
        
        # For single characters or failed word lookups, try kanji lookup
        if len(term) == 1:
            return self.lookup_kanji(term)
        
        # For multi-character words not found, aggregate character meanings
        if len(term) > 1:
            return self._aggregate_character_meanings(term)
        
        return None
    
    def _aggregate_character_meanings(self, word: str) -> Optional[Dict]:
        """
        Aggregate meanings from individual kanji when word lookup fails.
        
        Args:
            word: Japanese word
            
        Returns:
            Aggregated result or None
        """
        character_data = []
        meanings_list = []
        
        for char in word:
            kanji_data = self.lookup_kanji(char)
            if kanji_data:
                character_data.append(kanji_data)
                meanings_list.extend(kanji_data.get('meanings', []))
        
        if character_data:
            return {
                'term': word,
                'word': word,
                'meanings': meanings_list[:5],  # Top 5 combined meanings
                'source': 'kanjiapi',
                'type': 'aggregated',
                'characters': character_data
            }
        
        return None
    
    def _parse_kanji_response(self, character: str, data: Dict) -> Dict:
        """Parse KanjiAPI kanji response into standardized format."""
        return {
            'term': character,
            'kanji': data.get('kanji', character),
            'meanings': data.get('meanings', []),
            'kun_readings': data.get('kun_readings', []),
            'on_readings': data.get('on_readings', []),
            'grade': data.get('grade'),
            'jlpt': data.get('jlpt'),
            'stroke_count': data.get('stroke_count'),
            'unicode': data.get('unicode'),
            'source': 'kanjiapi',
            'type': 'kanji'
        }
    
    def _parse_word_response(self, word: str, data: List[Dict]) -> Optional[Dict]:
        """Parse KanjiAPI word response into standardized format."""
        if not data:
            return None
        
        # KanjiAPI returns a list of word entries
        entry = data[0] if isinstance(data, list) else data
        
        meanings = entry.get('meanings', [])
        if isinstance(meanings, list):
            meanings_list = []
            for m in meanings:
                if isinstance(m, dict):
                    glosses = m.get('glosses', [])
                    meanings_list.extend(glosses)
                elif isinstance(m, str):
                    meanings_list.append(m)
        else:
            meanings_list = [str(meanings)]
        
        return {
            'term': word,
            'word': word,
            'meanings': meanings_list[:5],  # Top 5 meanings
            'variants': entry.get('variants', []),
            'source': 'kanjiapi',
            'type': 'word'
        }


class ExternalDictionaryService:
    """
    Unified service for external dictionary lookups using KanjiAPI.dev.
    
    Features:
    - Unified API for both EN and VN translations
    - Batch lookups with caching
    - EDICT/KANJIDIC dictionary data (13,000+ kanji)
    - JLPT level information
    
    Usage:
        service = ExternalDictionaryService()
        
        # Single lookup (unified for both EN and VN)
        result = service.lookup('彼女')
        
        # Batch lookup
        results = service.batch_lookup(['彼女', '少女', '世界'])
    """
    
    def __init__(self, cache_dir: str = "cache/dictionary"):
        self.cache = DictionaryCache(cache_dir)
        self.kanjiapi = KanjiAPI(self.cache)
        
        # Statistics
        self._stats = {
            'lookups': 0,
            'cache_hits': 0,
            'api_calls': 0,
            'not_found': 0
        }
    
    def lookup(
        self,
        term: str,
        target_lang: str = 'vn'
    ) -> Optional[Dict]:
        """
        Look up a Japanese term using KanjiAPI.dev.
        
        Args:
            term: Japanese word/kanji to look up
            target_lang: Target language ('vn' or 'en' - both use same unified API)
            
        Returns:
            Lookup result with meanings or None if not found
        """
        self._stats['lookups'] += 1
        
        # KanjiAPI.dev provides English meanings that work for both EN and VN
        result = self.kanjiapi.lookup(term)
        
        if result:
            # Add target_lang to result for compatibility
            result['target_lang'] = target_lang
            return result
        
        self._stats['not_found'] += 1
        return None
    
    def batch_lookup(
        self,
        terms: List[str],
        target_lang: str = 'vn',
        max_api_calls: int = 20
    ) -> Dict[str, Dict]:
        """
        Look up multiple terms with rate limiting.
        
        Args:
            terms: List of Japanese terms
            target_lang: Target language ('vn' or 'en')
            max_api_calls: Maximum API calls to make (for rate limiting)
            
        Returns:
            Dictionary mapping terms to their lookup results
        """
        results = {}
        api_calls = 0
        
        for term in terms:
            # Check cache first (doesn't count as API call)
            cached = self.cache.get(term, 'kanjiapi')
            if cached:
                cached['target_lang'] = target_lang
                results[term] = cached
                self._stats['cache_hits'] += 1
                continue
            
            # Rate limit API calls
            if api_calls >= max_api_calls:
                logger.debug(f"[DICT] Rate limit reached, skipping: {term}")
                continue
            
            result = self.lookup(term, target_lang)
            if result:
                results[term] = result
            
            api_calls += 1
            self._stats['api_calls'] += 1
        
        return results
    
    def get_stats(self) -> Dict[str, int]:
        """Get lookup statistics."""
        return self._stats.copy()
    
    def format_for_prompt(self, results: Dict[str, Dict], target_lang: str = 'vn') -> str:
        """
        Format lookup results for translation prompt injection.
        
        Args:
            results: Dictionary of lookup results
            target_lang: Target language
            
        Returns:
            Formatted string for prompt
        """
        if not results:
            return ""
        
        lines = ["[EXTERNAL DICTIONARY REFERENCE - KanjiAPI.dev]"]
        
        for term, data in results.items():
            meanings = data.get('meanings', [])
            if meanings:
                # Join first 2-3 meanings
                meaning_str = '; '.join(meanings[:3])
                lines.append(f"  {term} = {meaning_str}")
                
                # Add readings if available
                kun_readings = data.get('kun_readings', [])
                on_readings = data.get('on_readings', [])
                if kun_readings or on_readings:
                    readings = []
                    if kun_readings:
                        readings.append(f"kun: {', '.join(kun_readings[:2])}")
                    if on_readings:
                        readings.append(f"on: {', '.join(on_readings[:2])}")
                    lines[-1] += f" ({'; '.join(readings)})"
                
                # Add JLPT level if available
                jlpt = data.get('jlpt')
                if jlpt:
                    lines[-1] += f" [JLPT N{jlpt}]"
        
        return '\n'.join(lines)


# Convenience functions
_default_service: Optional[ExternalDictionaryService] = None

def get_dictionary_service() -> ExternalDictionaryService:
    """Get or create the default dictionary service."""
    global _default_service
    if _default_service is None:
        _default_service = ExternalDictionaryService()
    return _default_service


def lookup_term(term: str, target_lang: str = 'vn') -> Optional[Dict]:
    """Quick lookup for a single term."""
    return get_dictionary_service().lookup(term, target_lang)


def batch_lookup_terms(terms: List[str], target_lang: str = 'vn') -> Dict[str, Dict]:
    """Quick batch lookup for multiple terms."""
    return get_dictionary_service().batch_lookup(terms, target_lang)


# Test
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    service = ExternalDictionaryService()
    
    # Test single kanji lookup
    print("\n=== Single Kanji Lookup Test ===")
    result = service.lookup('蛍')
    if result:
        print(f"  蛍 (Kanji):")
        print(f"    Meanings: {', '.join(result.get('meanings', []))}")
        print(f"    Kun readings: {', '.join(result.get('kun_readings', []))}")
        print(f"    On readings: {', '.join(result.get('on_readings', []))}")
        print(f"    JLPT: N{result.get('jlpt', 'N/A')}")
    
    # Test word lookup
    print("\n=== Word Lookup Test ===")
    result = service.lookup('彼女')
    if result:
        print(f"  彼女: {', '.join(result.get('meanings', []))}")
    
    # Test batch lookup
    print("\n=== Batch Lookup Test ===")
    terms = ['少女', '世界', '道', '気', '心']
    results = service.batch_lookup(terms)
    for term, data in results.items():
        meanings = ', '.join(data.get('meanings', [])[:3])
        jlpt = data.get('jlpt', '')
        jlpt_str = f" [JLPT N{jlpt}]" if jlpt else ""
        print(f"  {term}: {meanings}{jlpt_str}")
    
    # Show stats
    print("\n=== Statistics ===")
    stats = service.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test prompt formatting
    print("\n=== Prompt Formatting Test ===")
    prompt = service.format_for_prompt(results, target_lang='vn')
    print(prompt)
