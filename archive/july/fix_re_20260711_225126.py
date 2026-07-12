#!/data/data/com.termux/files/usr/bin/env python

"""
Fix regex patterns in Python files:
  - Detects re.sub / re.search / re.findall / re.match calls
  - Converts normal strings with escape sequences to raw strings
  - Replaces double backslashes '\\' with single backslashes '\'
  - Uses token-based detection with AST validation
  - Parallel processing with smart file filtering
  - Creates .bak backups before modification
  
Usage:
  python fix_regex.py [paths] [--workers N] [--no-backup] [--dry-run] [--verbose]
"""

import ast
import io
import sys
import tokenize
import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict, Any
from dataclasses import dataclass, field
from multiprocessing import Pool, cpu_count
from concurrent.futures import ProcessPoolExecutor
import time
import re
from collections import defaultdict

# Core re functions that take regex patterns as first argument
RE_FUNCTIONS = {
    "compile", "search", "match", "fullmatch", "split",
    "findall", "finditer", "sub", "subn"
}

# Skip these token types during processing
SKIP_TOKEN_TYPES = {
    tokenize.NL,
    tokenize.COMMENT,
    tokenize.NEWLINE,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.ENCODING,
    tokenize.TYPE_COMMENT,
    tokenize.ERRORTOKEN,
}

# Regex indicators that suggest a string should be raw
REGEX_INDICATORS = {
    r"\d", r"\w", r"\s", r"\S", r"\W", r"\D",
    r"\b", r"\B", r"\A", r"\Z", r"\z",
    r"[", r"]", r"(", r")", r"{", r"}",
    r"|", r"^", r"$", r"+", r"*", r"?",
    r".", r"\1", r"\2", r"\3", r"\4", r"\5",
    r"\6", r"\7", r"\8", r"\9", r"\0",
}


@dataclass
class StringModification:
    """Represents a string literal modification"""
    start: Tuple[int, int]  # (line, column)
    end: Tuple[int, int]
    original: str
    modified: str
    line_offset: int = 0


@dataclass
class ProcessingStats:
    """Statistics for file processing"""
    total_files: int = 0
    processed: int = 0
    modified: int = 0
    errors: int = 0
    skipped: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time


class RegexFixer:
    """Main class for fixing regex string literals"""
    
    def __init__(self, 
                 create_backup: bool = True,
                 dry_run: bool = False,
                 verbose: bool = False,
                 max_workers: Optional[int] = None):
        self.create_backup = create_backup
        self.dry_run = dry_run
        self.verbose = verbose
        self.max_workers = max_workers or min(cpu_count(), 8)
        self.stats = ProcessingStats()
        
    def should_convert_string(self, content: str) -> bool:
        """Check if a string literal should be converted to raw"""
        if not content:
            return False
            
        # Count escape sequences
        escape_count = 0
        i = 0
        while i < len(content) - 1:
            if content[i] == '\\':
                # Check if it's a valid Python escape sequence
                if content[i+1] in '\\abfnrtv"\'01234567xNuU':
                    escape_count += 1
                    if escape_count >= 2:
                        return True
                    # Check if this escape is part of a regex pattern
                    for indicator in REGEX_INDICATORS:
                        if content[i:i+len(indicator)] == indicator:
                            return True
                i += 1
            i += 1
            
        # Check for regex patterns even without escapes
        if any(indicator in content for indicator in REGEX_INDICATORS):
            return True
            
        return False
    
    def parse_string_literal(self, token_str: str) -> Tuple[str, str, str, bool]:
        """
        Parse a string literal and return (prefix, quote, content, is_raw)
        Example: r"hello" -> ("r", '"', "hello", True)
        """
        # Find where the string content starts
        prefix_end = 0
        for ch in token_str:
            if ch in ('"', "'"):
                break
            prefix_end += 1
        else:
            return token_str, "", "", False
        
        prefix = token_str[:prefix_end]
        is_raw = 'r' in prefix.lower()
        is_fstring = 'f' in prefix.lower()
        is_bytes = 'b' in prefix.lower()
        
        # Determine quote type and length
        quote_char = token_str[prefix_end]
        quote_len = 1
        if (len(token_str) >= prefix_end + 3 and 
            token_str[prefix_end:prefix_end + 3] == quote_char * 3):
            quote_len = 3
            
        opening = quote_char * quote_len
        content_start = prefix_end + quote_len
        content_end = len(token_str) - quote_len
        
        if content_end <= content_start:
            return prefix, opening, "", is_raw
            
        content = token_str[content_start:content_end]
        return prefix, opening, content, is_raw
    
    def convert_string(self, token_str: str) -> Optional[str]:
        """Convert a string literal to raw format"""
        prefix, opening, content, is_raw = self.parse_string_literal(token_str)
        
        # Skip if already raw
        if is_raw:
            return None
            
        # Skip if not a regular string (bytes, etc.)
        if 'b' in prefix.lower():
            return None
            
        # Check if conversion is needed
        if not self.should_convert_string(content):
            return None
            
        # Fix double backslashes
        new_content = content.replace("\\\\", "\\")
        
        # Preserve f-string prefix if present
        new_prefix = prefix
        if 'f' in prefix.lower() and 'r' not in prefix.lower():
            # Add r to f-string
            new_prefix = 'rf' + prefix.replace('f', '').replace('F', '')
        elif 'r' not in prefix.lower():
            new_prefix = 'r' + prefix
            
        return f"{new_prefix}{opening}{new_content}{opening}"
    
    def process_tokens(self, code: str) -> List[StringModification]:
        """Process tokens and find string literals to convert"""
        modifications = []
        
        try:
            # Tokenize the code
            tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
        except tokenize.TokenError:
            return modifications
        
        # Filter to relevant tokens (name, op, string)
        relevant = []
        for tok in tokens:
            if tok.type in SKIP_TOKEN_TYPES:
                continue
            if tok.type in (tokenize.NAME, tokenize.OP, tokenize.STRING):
                relevant.append(tok)
            elif tok.type == tokenize.NUMBER:
                # Numbers aren't needed but keep for context
                relevant.append(tok)
        
        # Look for re.function(pattern) pattern
        i = 0
        while i < len(relevant) - 4:
            # Check for: re . function ( string
            if (relevant[i].type == tokenize.NAME and 
                relevant[i].string == 're' and
                i + 1 < len(relevant) and
                relevant[i+1].type == tokenize.OP and
                relevant[i+1].string == '.' and
                i + 2 < len(relevant) and
                relevant[i+2].type == tokenize.NAME and
                relevant[i+2].string in RE_FUNCTIONS and
                i + 3 < len(relevant) and
                relevant[i+3].type == tokenize.OP and
                relevant[i+3].string == '(' and
                i + 4 < len(relevant) and
                relevant[i+4].type == tokenize.STRING):
                
                str_token = relevant[i+4]
                new_str = self.convert_string(str_token.string)
                
                if new_str is not None and new_str != str_token.string:
                    modifications.append(
                        StringModification(
                            start=str_token.start,
                            end=str_token.end,
                            original=str_token.string,
                            modified=new_str
                        )
                    )
                i += 5
            else:
                i += 1
                
        return modifications
    
    def apply_modifications(self, code: str, modifications: List[StringModification]) -> str:
        """Apply modifications to the source code"""
        if not modifications:
            return code
            
        lines = code.splitlines(keepends=True)
        
        # Calculate line offsets
        line_offsets = [0]
        for line in lines:
            line_offsets.append(line_offsets[-1] + len(line))
        
        # Sort modifications by position (reverse order for safe replacement)
        sorted_mods = sorted(modifications, key=lambda x: (x.start[0], x.start[1]), reverse=True)
        
        # Apply modifications
        result_parts = []
        last_end = len(code)
        
        for mod in sorted_mods:
            start_abs = line_offsets[mod.start[0] - 1] + mod.start[1]
            end_abs = line_offsets[mod.end[0] - 1] + mod.end[1]
            
            # Add the unmodified part between current position and this modification
            result_parts.append(code[end_abs:last_end])
            
            # Add the modified string
            result_parts.append(mod.modified)
            
            last_end = start_abs
        
        # Add the beginning of the file
        result_parts.append(code[:last_end])
        
        # Reverse back to original order
        result_parts.reverse()
        
        return ''.join(result_parts)
    
    def validate_code(self, code: str) -> bool:
        """Validate that the code is syntactically correct"""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False
    
    def process_file(self, filepath: Path) -> Tuple[Path, bool, str]:
        """Process a single Python file"""
        try:
            original_code = filepath.read_text(encoding='utf-8')
        except Exception as e:
            return (filepath, False, f"Failed to read: {e}")
        
        # Quick check for re calls
        if 're.' not in original_code:
            return (filepath, True, "No re calls found")
        
        # Find modifications
        modifications = self.process_tokens(original_code)
        
        if not modifications:
            return (filepath, True, "No changes needed")
        
        if self.verbose:
            print(f"Found {len(modifications)} modification(s) in {filepath.name}")
            for mod in modifications:
                print(f"  {mod.original} -> {mod.modified}")
        
        # Apply modifications
        new_code = self.apply_modifications(original_code, modifications)
        
        # Validate the result
        if not self.validate_code(new_code):
            return (filepath, False, "Validation failed - syntax error after conversion")
        
        # Handle dry run
        if self.dry_run:
            return (filepath, True, f"Would modify {len(modifications)} string(s)")
        
        # Create backup
        if self.create_backup:
            backup_path = filepath.with_suffix(filepath.suffix + '.bak')
            try:
                shutil.copy2(filepath, backup_path)
            except Exception as e:
                return (filepath, False, f"Failed to create backup: {e}")
        
        # Write the new code
        try:
            filepath.write_text(new_code, encoding='utf-8')
            return (filepath, True, f"✓ Modified {len(modifications)} string(s)")
        except Exception as e:
            return (filepath, False, f"Failed to write: {e}")
    
    def collect_files(self, paths: List[Path]) -> List[Path]:
        """Collect Python files from given paths"""
        python_files = set()
        exclude_dirs = {
            '.venv', 'venv', 'env', '__pycache__', 
            '.git', '.hg', '.svn', 'node_modules',
            'dist', 'build', '.tox', '.pytest_cache'
        }
        
        for path in paths:
            if not path.exists():
                print(f"Warning: Path does not exist: {path}", file=sys.stderr)
                continue
                
            if path.is_file():
                if path.suffix == '.py':
                    python_files.add(path)
            elif path.is_dir():
                for py_file in path.rglob('*.py'):
                    # Skip excluded directories
                    if any(part in exclude_dirs for part in py_file.parts):
                        continue
                    python_files.add(py_file)
        
        return sorted(python_files)
    
    def process_files(self, files: List[Path]) -> List[Tuple[Path, bool, str]]:
        """Process files in parallel"""
        if not files:
            return []
        
        self.stats.total_files = len(files)
        
        if len(files) == 1 or self.max_workers <= 1:
            # Process sequentially
            results = []
            for i, filepath in enumerate(files, 1):
                if self.verbose and i % 10 == 0:
                    print(f"Progress: {i}/{len(files)}", flush=True)
                result = self.process_file(filepath)
                results.append(result)
                self._update_stats(result)
            return results
        else:
            # Process in parallel
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                futures = [executor.submit(self.process_file, f) for f in files]
                results = []
                
                for i, future in enumerate(futures, 1):
                    try:
                        result = future.result()
                        results.append(result)
                        self._update_stats(result)
                        if self.verbose and i % 10 == 0:
                            print(f"Progress: {i}/{len(files)}", flush=True)
                    except Exception as e:
                        results.append((files[i-1], False, f"Error: {e}"))
                        self.stats.errors += 1
                
                return results
    
    def _update_stats(self, result: Tuple[Path, bool, str]):
        """Update processing statistics"""
        _, success, message = result
        if success:
            self.stats.processed += 1
            if 'Modified' in message or 'Would modify' in message:
                self.stats.modified += 1
            elif 'No changes' in message:
                self.stats.skipped += 1
        else:
            self.stats.errors += 1
    
    def print_summary(self, results: List[Tuple[Path, bool, str]]):
        """Print processing summary"""
        if not results:
            print("\nNo files processed.")
            return
        
        print("\n" + "=" * 80)
        
        # Group results
        modified = []
        unchanged = []
        errors = []
        
        for filepath, success, message in results:
            if not success:
                errors.append((filepath, message))
            elif 'Modified' in message or 'Would modify' in message:
                modified.append((filepath, message))
            else:
                unchanged.append((filepath, message))
        
        # Print modified files
        if modified:
            print("\n📝 Modified files:")
            for filepath, message in modified:
                rel_path = self._get_relative_path(filepath)
                print(f"  ✓ {rel_path}")
                if self.verbose:
                    print(f"    {message}")
        
        # Print errors
        if errors:
            print("\n❌ Errors:")
            for filepath, message in errors:
                rel_path = self._get_relative_path(filepath)
                print(f"  ✗ {rel_path}: {message}")
        
        # Print summary
        print("\n" + "=" * 80)
        print(f"\n📊 Summary:")
        print(f"  Total files:     {self.stats.total_files}")
        print(f"  Processed:       {self.stats.processed}")
        print(f"  Modified:        {self.stats.modified}")
        print(f"  Unchanged:       {self.stats.skipped}")
        print(f"  Errors:          {self.stats.errors}")
        print(f"  Time elapsed:    {self.stats.elapsed:.2f}s")
        print(f"  Workers:         {self.max_workers}")
        print(f"  Backup:          {'Enabled' if self.create_backup else 'Disabled'}")
        print(f"  Dry run:         {'Yes' if self.dry_run else 'No'}")
    
    def _get_relative_path(self, path: Path) -> str:
        """Get relative path from current directory"""
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fix regex string literals in Python files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix all Python files in current directory
  python fix_regex.py
  
  # Fix specific files or directories
  python fix_regex.py src/ tests/test_regex.py
  
  # Use 4 parallel workers, disable backups
  python fix_regex.py --workers 4 --no-backup
  
  # Preview changes without modifying files
  python fix_regex.py --dry-run --verbose
        """
    )
    
    parser.add_argument(
        'paths', 
        nargs='*',
        help='Files or directories to process (default: current directory)'
    )
    parser.add_argument(
        '--workers', '-w',
        type=int,
        help=f'Number of parallel workers (default: min(CPU cores, 8))'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Disable backup creation'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Minimize output'
    )
    
    args = parser.parse_args()
    
    # Set up paths
    if args.paths:
        paths = [Path(p).resolve() for p in args.paths]
    else:
        paths = [Path.cwd()]
    
    # Create fixer instance
    fixer = RegexFixer(
        create_backup=not args.no_backup,
        dry_run=args.dry_run,
        verbose=args.verbose,
        max_workers=args.workers
    )
    
    # Collect files
    if not args.quiet:
        print(f"📁 Collecting Python files from {len(paths)} path(s)...")
    
    files = fixer.collect_files(paths)
    
    if not files:
        print("No Python files found.")
        return
    
    if not args.quiet:
        print(f"✅ Found {len(files)} Python files")
        print(f"🔧 Processing with {fixer.max_workers} worker(s)")
        print(f"💾 Backup: {'Enabled' if fixer.create_backup else 'Disabled'}")
        if fixer.dry_run:
            print("🔍 DRY RUN - No files will be modified")
        print()
    
    # Process files
    results = fixer.process_files(files)
    
    # Print summary
    fixer.print_summary(results)
    
    # Exit with error code if there were errors
    if fixer.stats.errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
