#!/usr/bin/env python3
"""
TikTok Video Editor with Google Sheets Integration
Rapidly edit videos by cutting off first 0.5s and last 0.25s, adding overlay text from Google Sheets
Uses FFmpeg for professional text overlay with custom font support
Automatically selects overlay text based on video type from Google Sheets data
"""

import os
import sys
import subprocess
import shutil
import textwrap
import re
from pathlib import Path
import random
import json

# Google Sheets imports
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False

class TikTokEditor:
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.input_dir = self.script_dir / "input-videos"
        self.output_dir = self.script_dir / "output-videos"
        self.font_path = self.script_dir / "assets" / "TikTokDisplay-Medium.ttf"  # Font in assets folder
        self.credentials_path = self.script_dir / "assets" / "credentials.json"  # Google Sheets credentials
        
        # Google Sheets configuration
        self.sheet_id = None  # Will be set from config or user input
        self.worksheet_name = "Sheet1"  # Default worksheet name
        self.gc = None  # Google Sheets client
        self.worksheet = None  # Current worksheet
        
        # Trim settings
        self.start_trim = 0.5  # Cut off first 0.5 seconds
        self.end_trim = 0.25   # Cut off last 0.25 seconds
        
        # Supported video file types
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}
        
        # Valid video types (lowercase for filename matching)
        self.valid_types = {'romantic', 'crying', 'confused', 'surprised', 'sad'}
        
        # Expected headers for Google Sheets
        self.expected_headers = ['used?', 'mentions toffee?', 'type', 'overlay text']
    
    def check_dependencies(self):
        """Check if FFmpeg and Google Sheets libraries are installed"""
        # Check FFmpeg
        if not shutil.which('ffmpeg'):
            print("❌ FFmpeg is not installed!")
            print("Please install FFmpeg:")
            print("  Mac: brew install ffmpeg")
            print("  Linux: sudo apt-get install ffmpeg") 
            print("  Windows: Download from ffmpeg.org")
            return False
        print("✅ FFmpeg found")
        
        # Check Google Sheets libraries
        if not GOOGLE_SHEETS_AVAILABLE:
            print("❌ Google Sheets libraries not installed!")
            print("Please install required packages:")
            print("  pip install gspread google-auth")
            return False
        print("✅ Google Sheets libraries found")
        
        return True
    
    def setup_google_sheets(self):
        """Set up Google Sheets connection"""
        # Check credentials file
        if not self.credentials_path.exists():
            print(f"❌ Credentials file not found: {self.credentials_path}")
            print("Please:")
            print("1. Go to Google Cloud Console")
            print("2. Create a service account")
            print("3. Download the JSON credentials file")
            print("4. Save it as 'credentials.json' in the assets folder")
            return False
        
        try:
            # Set up credentials
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_file(
                str(self.credentials_path), 
                scopes=scopes
            )
            
            # Initialize the client
            self.gc = gspread.authorize(credentials)
            print("✅ Google Sheets authentication successful")
            
            return True
            
        except Exception as e:
            print(f"❌ Error setting up Google Sheets: {str(e)}")
            return False
    
    def get_sheet_id_from_user(self):
        """Get Google Sheets ID from user input or config"""
        config_file = self.script_dir / "sheet_config.txt"
        
        # Try to load from config file first
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    saved_id = f.read().strip()
                    if saved_id:
                        print(f"📋 Using saved Google Sheets ID from config")
                        return saved_id
            except:
                pass
        
        # Get from user input
        print("\n📋 Google Sheets Setup")
        print("=" * 30)
        print("Please provide your Google Sheets ID.")
        print("You can find it in the URL: https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit")
        print("\nExample URL: https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit")
        print("Sheet ID would be: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
        
        sheet_id = input("\nEnter your Google Sheets ID: ").strip()
        
        if sheet_id:
            # Save to config file for future use
            try:
                with open(config_file, 'w') as f:
                    f.write(sheet_id)
                print("✅ Sheet ID saved to config file")
            except:
                print("⚠️  Could not save Sheet ID to config file")
            
            return sheet_id
        
        return None
    
    def connect_to_sheet(self):
        """Connect to the specific Google Sheet"""
        if not self.sheet_id:
            self.sheet_id = self.get_sheet_id_from_user()
            
        if not self.sheet_id:
            print("❌ No Google Sheets ID provided")
            return False
        
        try:
            # Open the spreadsheet
            spreadsheet = self.gc.open_by_key(self.sheet_id)
            print(f"✅ Connected to spreadsheet: {spreadsheet.title}")
            
            # Get the first worksheet (or specified worksheet)
            try:
                self.worksheet = spreadsheet.worksheet(self.worksheet_name)
            except:
                # If specified worksheet doesn't exist, use the first one
                self.worksheet = spreadsheet.get_worksheet(0)
                self.worksheet_name = self.worksheet.title
            
            print(f"✅ Using worksheet: {self.worksheet_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error connecting to Google Sheet: {str(e)}")
            print("Please check:")
            print("1. Sheet ID is correct")
            print("2. Service account has access to the sheet")
            print("3. Sheet is not deleted or private")
            return False
    
    def check_sheet_format(self):
        """Check if Google Sheet has correct format"""
        try:
            # Get all records to check format
            records = self.worksheet.get_all_records()
            
            if not records:
                print("❌ Google Sheet is empty or has no data rows")
                print("Please add header row and data to your Google Sheet")
                return False
            
            # Check headers by looking at the first record's keys
            headers = list(records[0].keys())
            
            # Normalize headers (strip whitespace, handle case variations)
            normalized_headers = [h.strip().lower() for h in headers]
            expected_normalized = [h.strip().lower() for h in self.expected_headers]
            
            if set(normalized_headers) != set(expected_normalized):
                print(f"❌ Google Sheet headers incorrect.")
                print(f"Expected: {self.expected_headers}")
                print(f"Found: {headers}")
                print("\nPlease ensure your Google Sheet has exactly these column headers:")
                for header in self.expected_headers:
                    print(f"  • {header}")
                return False
            
            print("✅ Google Sheet format validated")
            print(f"📊 Found {len(records)} data rows")
            return True
            
        except Exception as e:
            print(f"❌ Error checking sheet format: {str(e)}")
            return False
    
    def extract_type_from_filename(self, filename):
        """Extract video type from filename"""
        filename_lower = filename.lower()
        
        for video_type in self.valid_types:
            if video_type in filename_lower:
                return video_type.capitalize()  # Return with capital first letter to match sheet
        
        return None
    
    def find_next_overlay_text(self, video_type):
        """Find next unused overlay text for the given video type"""
        try:
            # Get all records
            records = self.worksheet.get_all_records()
            
            # Find matching unused row
            for i, record in enumerate(records):
                # Normalize the comparison
                record_type = str(record.get('type', '')).strip()
                record_used = str(record.get('used?', '')).strip().upper()
                
                if (record_type.lower() == video_type.lower() and 
                    record_used == 'FALSE'):
                    
                    overlay_text = str(record.get('overlay text', '')).strip()
                    
                    # Mark as used in Google Sheets (row numbers start at 1, plus 1 for header)
                    row_number = i + 2
                    self.worksheet.update_cell(row_number, 1, 'TRUE')  # Column 1 is 'used?'
                    
                    print(f"✅ Found overlay text for type '{video_type}'")
                    print(f"📝 Text: {overlay_text}")
                    print(f"📋 Marked row {row_number} as used in Google Sheets")
                    
                    return overlay_text
            
            print(f"❌ No unused overlay text found for type '{video_type}'")
            return None
            
        except Exception as e:
            print(f"❌ Error accessing Google Sheets data: {str(e)}")
            return None
    
    def find_video_file(self):
        """Find the first video file in the input directory"""
        if not self.input_dir.exists():
            return None
            
        for file_path in self.input_dir.iterdir():
            if file_path.suffix.lower() in self.video_extensions:
                return file_path
        return None
    
    def find_all_video_files(self):
        """Find all video files in the input directory"""
        if not self.input_dir.exists():
            return []
            
        video_files = []
        for file_path in self.input_dir.iterdir():
            if file_path.suffix.lower() in self.video_extensions:
                video_files.append(file_path)
        
        return sorted(video_files)  # Sort for consistent processing order
    
    def get_video_duration(self, video_path):
        """Get video duration in seconds using FFprobe"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())
        except:
            return 0
    
    def calculate_trimmed_duration(self, original_duration):
        """Calculate the final duration after trimming start and end"""
        trimmed_duration = original_duration - self.start_trim - self.end_trim
        
        # Ensure we don't get negative duration
        if trimmed_duration <= 0:
            print(f"⚠️  Warning: Video too short for trimming. Original: {original_duration:.1f}s")
            return max(0.1, original_duration * 0.8)  # Use 80% of original as fallback
        
        return trimmed_duration
    
    def get_system_font_path(self):
        """Get a suitable font path for the current OS"""
        import platform
        system = platform.system()
        
        if system == "Darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Avenir.ttc",
                "/Library/Fonts/Arial.ttf"
            ]
        elif system == "Windows":
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/Arial.ttf",
                "C:/Windows/Fonts/calibri.ttf"
            ]
        else:  # Linux
            font_paths = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf"
            ]
        
        # Find first available font
        for font in font_paths:
            if Path(font).exists():
                return font
        return None
    
    def wrap_text_for_margins(self, text, margin_percent=5):
        """Wrap text to fit within margins of the video"""
        # With 5% margins and 75pt font, approximately 22-24 chars per line
        # This ensures text fits within the 90% available width
        chars_per_line = 23
        
        # Use textwrap to wrap the text
        wrapped = textwrap.fill(text, width=chars_per_line, break_long_words=False)
        return wrapped
    
    def edit_video_with_text(self, video_path, overlay_text, trimmed_duration):
        """Edit video with FFmpeg text overlay and trimming"""
        print("🎬 Processing video with text overlay and trimming...")
        
        # Wrap text for margins (5% on each side)
        wrapped_text = self.wrap_text_for_margins(overlay_text, margin_percent=5)
        
        # Create temporary text file to avoid escaping issues
        text_file = self.script_dir / "overlay_text.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(wrapped_text)
        
        # Determine font to use
        font_param = ''
        if self.font_path.exists():
            print(f"✅ Using custom font: {self.font_path.name}")
            font_param = f":fontfile='{str(self.font_path)}'"
        else:
            system_font = self.get_system_font_path()
            if system_font:
                print(f"✅ Using system font: {Path(system_font).name}")
                font_param = f":fontfile='{system_font}'"
            else:
                print("✅ Using FFmpeg default font")
                font_param = ''
        
        # Generate output filename
        input_name = video_path.stem
        output_path = self.output_dir / f"{input_name}_edited.mp4"
        
        rand_font_height = random.uniform(0.30, 0.70)

        # Build drawtext filter using textfile (text shows for entire trimmed duration)
        drawtext_filter = (
            f"drawtext="
            f"textfile='{str(text_file)}'"
            f"{font_param}"
            f":fontsize=30"  # 75pt font size
            f":fontcolor=white"
            f":borderw=2"  # Black border thickness
            f":bordercolor=black" 
            f":x=(w-text_w)/2"  # Center horizontally
            f":y=(h-text_h)*{rand_font_height}"  # Center vertically (top of text centered)
            f":text_align=C"  # Center align text
            f":enable='between(t,0,{trimmed_duration})'"  # Show for full trimmed duration
        )
        
        # FFmpeg command: skip first 0.5s, cut to trimmed duration, add text overlay
        cmd = [
            'ffmpeg',
            '-ss', str(self.start_trim),  # Skip first 0.5 seconds
            '-i', str(video_path),
            '-vf', f"[in]{drawtext_filter}[out]",
            '-t', str(trimmed_duration),  # Duration after trimming
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-y',  # Overwrite output file
            str(output_path)
        ]
        
        try:
            # Run FFmpeg with progress monitoring
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            stderr_lines = []
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                stderr_lines.append(line)
                # Show progress
                if 'time=' in line:
                    time_str = line.split('time=')[1].split()[0]
                    print(f"  Processing: {time_str}", end='\r')
            
            process.wait()
            
            # Clean up text file
            if text_file.exists():
                text_file.unlink()
            
            if process.returncode == 0:
                print(f"\n✅ Video created successfully: {output_path.name}")
                return True
            else:
                print(f"\n❌ FFmpeg error occurred")
                # Try fallback without custom font
                return self.edit_video_fallback(video_path, overlay_text, trimmed_duration)
                
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            # Clean up text file on error
            if text_file.exists():
                text_file.unlink()
            return False
    
    def edit_video_fallback(self, video_path, overlay_text, trimmed_duration):
        """Fallback method without custom font"""
        print("🔄 Retrying with simplified text overlay...")
        
        # Wrap text and create temporary file
        wrapped_text = self.wrap_text_for_margins(overlay_text, margin_percent=5)
        text_file = self.script_dir / "overlay_text.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(wrapped_text)
        
        # Generate output filename
        input_name = video_path.stem
        output_path = self.output_dir / f"{input_name}_edited.mp4"
        rand_font_height = random.uniform(0.30, 0.70)

        # Build filter without custom font
        drawtext_filter = (
            f"drawtext="
            f"textfile='{str(text_file)}'"
            f":fontsize=30"
            f":fontcolor=white"
            f":borderw=2"
            f":bordercolor=black"
            f":x=(w-text_w)/2"
            f":y=(h-text_h)*{rand_font_height}"
            f":text_align=C"
            f":enable='between(t,0,{trimmed_duration})'"
        )
        
        cmd = [
            'ffmpeg',
            '-ss', str(self.start_trim),  # Skip first 0.5 seconds
            '-i', str(video_path),
            '-vf', f"{drawtext_filter}",
            '-t', str(trimmed_duration),  # Duration after trimming
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-y',
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean up text file
            if text_file.exists():
                text_file.unlink()
            
            if result.returncode == 0:
                print(f"✅ Video created successfully: {output_path.name}")
                return True
            else:
                print("❌ Fallback failed, creating video without text...")
                return self.edit_video_no_text(video_path, trimmed_duration)
        except Exception as e:
            print(f"❌ Fallback error: {str(e)}")
            if text_file.exists():
                text_file.unlink()
            return False
    
    def edit_video_no_text(self, video_path, trimmed_duration):
        """Edit video without text overlay (trim only)"""
        print("⚠️  Creating video without text overlay...")
        
        # Generate output filename
        input_name = video_path.stem
        output_path = self.output_dir / f"{input_name}_edited.mp4"
        
        cmd = [
            'ffmpeg',
            '-ss', str(self.start_trim),  # Skip first 0.5 seconds
            '-i', str(video_path),
            '-t', str(trimmed_duration),  # Duration after trimming
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-y',
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ Video created successfully: {output_path.name}")
                print("⚠️  Note: Text overlay was omitted due to processing issues")
                return True
            else:
                print("❌ Video creation failed")
                return False
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return False
    
    def show_sheet_statistics(self):
        """Display statistics about the Google Sheets data"""
        try:
            records = self.worksheet.get_all_records()
            
            print("\n📊 Google Sheets Statistics:")
            print("=" * 35)
            
            # Count by type and usage
            type_stats = {}
            for record in records:
                video_type = str(record.get('type', '')).strip()
                used = str(record.get('used?', '')).strip().upper() == 'TRUE'
                
                if video_type not in type_stats:
                    type_stats[video_type] = {'total': 0, 'used': 0, 'available': 0}
                
                type_stats[video_type]['total'] += 1
                if used:
                    type_stats[video_type]['used'] += 1
                else:
                    type_stats[video_type]['available'] += 1
            
            for video_type, stats in type_stats.items():
                if video_type:  # Skip empty types
                    print(f"{video_type}: {stats['available']}/{stats['total']} available")
            
        except Exception as e:
            print(f"❌ Error reading Google Sheets statistics: {str(e)}")
    
    def process_single_video(self, video_file):
        """Process a single video file"""
        print(f"\n{'='*60}")
        print(f"🎬 Processing: {video_file.name}")
        print(f"{'='*60}")
        
        # Extract video type from filename
        video_type = self.extract_type_from_filename(video_file.stem)
        if not video_type:
            print(f"❌ Could not determine video type from filename: {video_file.name}")
            print("   Filename should contain one of: romantic, crying, confused, surprised, sad")
            return False
        
        print(f"🎭 Detected type: {video_type}")
        
        # Get overlay text from Google Sheets
        overlay_text = self.find_next_overlay_text(video_type)
        if not overlay_text:
            print(f"❌ No available overlay text for type '{video_type}'")
            return False
        
        # Get video info and calculate trimming
        original_duration = self.get_video_duration(video_file)
        trimmed_duration = self.calculate_trimmed_duration(original_duration)
        
        print(f"📊 Original duration: {original_duration:.1f}s")
        print(f"✂️  Trimming: -{self.start_trim}s (start) and -{self.end_trim}s (end)")
        print(f"🎯 Final duration: {trimmed_duration:.1f}s")
        
        # Check if video is long enough for trimming
        if original_duration < (self.start_trim + self.end_trim + 0.5):
            print(f"⚠️  Warning: Video may be too short for optimal trimming")
        
        # Show text preview
        wrapped_preview = self.wrap_text_for_margins(overlay_text, margin_percent=5)
        print(f"📝 Overlay text preview:")
        for line in wrapped_preview.split('\n'):
            print(f"    {line}")
        
        print(f"🔄 Starting video processing...")
        
        # Process the video with text and trimming
        success = self.edit_video_with_text(video_file, overlay_text, trimmed_duration)
        
        if success:
            print(f"✅ Successfully processed: {video_file.name}")
        else:
            print(f"❌ Failed to process: {video_file.name}")
        
        return success
    
    def run(self):
        """Main execution function"""
        print("🎵 TikTok Video Editor with Google Sheets Integration - Batch Mode (with Trimming)")
        print("=" * 80)
        
        # Check dependencies
        if not self.check_dependencies():
            return False
        
        # Set up Google Sheets connection
        if not self.setup_google_sheets():
            return False
        
        # Connect to the specific sheet
        if not self.connect_to_sheet():
            return False
        
        # Check sheet format
        if not self.check_sheet_format():
            return False
        
        # Show Google Sheets statistics
        self.show_sheet_statistics()
        
        # Ensure directories exist
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all video files
        video_files = self.find_all_video_files()
        if not video_files:
            print(f"\n❌ No video files found in {self.input_dir}")
            print("Please add video files (.mp4, .avi, .mov, etc.) to the input-videos folder.")
            print("Filenames should contain one of: romantic, crying, confused, surprised, sad")
            return False
        
        print(f"\n📹 Found {len(video_files)} video file(s) to process:")
        for i, video_file in enumerate(video_files, 1):
            video_type = self.extract_type_from_filename(video_file.stem)
            type_info = f" ({video_type})" if video_type else " (⚠️ unknown type)"
            print(f"   {i}. {video_file.name}{type_info}")
        
        # Show trimming settings
        print(f"\n✂️  Trimming settings:")
        print(f"   • Remove first {self.start_trim}s of each video")
        print(f"   • Remove last {self.end_trim}s of each video")
        print(f"   • Total reduction: {self.start_trim + self.end_trim}s per video")
        
        # Check for custom font
        if self.font_path.exists():
            print(f"\n🎨 Custom font available: {self.font_path.name}")
        else:
            print("\n🎨 Custom font not found, will use system font")
        
        print(f"\n📋 Using Google Sheet: {self.worksheet.spreadsheet.title}")
        print(f"📄 Worksheet: {self.worksheet_name}")
        
        # Process each video
        successful_videos = []
        failed_videos = []
        
        for i, video_file in enumerate(video_files, 1):
            print(f"\n🎯 Progress: {i}/{len(video_files)}")
            
            if self.process_single_video(video_file):
                successful_videos.append(video_file.name)
            else:
                failed_videos.append(video_file.name)
        
        # Final summary
        print(f"\n{'='*60}")
        print(f"🎉 BATCH PROCESSING COMPLETE")
        print(f"{'='*60}")
        print(f"✅ Successfully processed: {len(successful_videos)}/{len(video_files)} videos")
        
        if successful_videos:
            print(f"\n📂 Successfully processed videos:")
            for video_name in successful_videos:
                print(f"   ✓ {video_name}")
        
        if failed_videos:
            print(f"\n❌ Failed to process:")
            for video_name in failed_videos:
                print(f"   ✗ {video_name}")
        
        if successful_videos:
            print(f"\n📁 Check the output-videos folder for your processed videos.")
            print(f"✨ Features applied to each video:")
            print(f"   • Trimmed first {self.start_trim}s and last {self.end_trim}s")
            print(f"   • Type-specific text overlay from Google Sheets")
            print(f"   • Professional text styling (30pt font)")
            print(f"   • White text with black border")
            print(f"   • Centered positioning with 5% margins")
            print(f"   • Original filenames preserved")
            print(f"   • Google Sheets automatically updated")
        
        return len(successful_videos) > 0

def main():
    """Entry point"""
    print("Setting up TikTok Video Editor with Google Sheets...")
    
    # Check if required packages are available
    if not GOOGLE_SHEETS_AVAILABLE:
        print("\n❌ Required packages not installed!")
        print("Please install the required packages by running:")
        print("pip install gspread google-auth")
        print("\nOr if using conda:")
        print("conda install -c conda-forge gspread google-auth")
        sys.exit(1)
    
    editor = TikTokEditor()
    success = editor.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()