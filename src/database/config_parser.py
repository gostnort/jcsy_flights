import yaml
import re
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Union

class ConfigParser:
    """
    A configuration-driven parser that processes data based on YAML schema
    """
    
    def __init__(self, config_path: str):
        """
        Initialize with path to configuration file
        
        Args:
            config_path: Path to the YAML configuration file
        """
        self.config = self._load_config(config_path)
        self.transforms = self._prepare_transforms()
        self.type_converters = self._prepare_type_converters()
        self.special_parsers = self._prepare_special_parsers()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
            
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _prepare_transforms(self) -> Dict[str, Callable]:
        """Prepare transform functions from configuration"""
        transforms = {}
        for name, transform_config in self.config.get('transforms', {}).items():
            transforms[name] = eval(transform_config['python'])
        return transforms
    
    def _prepare_type_converters(self) -> Dict[str, Callable]:
        """Prepare type converter functions from configuration"""
        converters = {}
        for type_name, type_config in self.config.get('types', {}).items():
            converters[type_name] = eval(type_config['python'])
        return converters
        
    def _prepare_special_parsers(self) -> Dict[str, Callable]:
        """Prepare special parser functions for complex formats"""
        parsers = {}
        
        # Local function to extract parsers from special_parsers section
        def setup_parsers():
            special_parsers = {}
            for parser_section in self.config.get('special_parsers', {}).items():
                parser_name, parser_config = parser_section
                # For multi-line functions
                if 'python' in parser_config and isinstance(parser_config['python'], str):
                    parser_code = parser_config['python']
                    # Execute the function definition and store the function object
                    local_vars = {}
                    exec(parser_code, globals(), local_vars)
                    # Extract the function from local variables
                    for var_name, var_value in local_vars.items():
                        if callable(var_value) and var_name == parser_name:
                            special_parsers[parser_name] = var_value
            return special_parsers
            
        # Use the nested function to set up special parsers in this scope
        parsers = setup_parsers()
        
        # Keep a reference to the parsers in the class instance
        self.special_parsers_dict = parsers
        
        return parsers
    
    def parse_content(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse content string according to configuration
        
        Args:
            content: The string content to parse
            
        Returns:
            List of dictionaries containing parsed data
        """
        lines = content.strip().split('\n')
        results = []
        
        # Track header information
        current_header = {}
        
        for line in lines:
            line = line.rstrip()
            if not line:
                continue
                
            # Check if this is a header line
            header_pattern = self.config.get('header', {}).get('pattern')
            if header_pattern and re.match(header_pattern, line):
                current_header = self._parse_line(line, 'header')
                continue
                
            # Check if this is a flight line
            flight_pattern = self.config.get('flight', {}).get('pattern')
            if flight_pattern and re.match(flight_pattern, line):
                flight_data = self._parse_line(line, 'flight')
                # Merge with header data
                merged_data = {**current_header, **flight_data, 'line': line}
                results.append(merged_data)
                
        return results
    
    def _parse_line(self, line: str, section_name: str) -> Dict[str, Any]:
        """Parse a single line according to configuration section"""
        result = {}
        fields = self.config.get(section_name, {}).get('fields', [])
        
        for field in fields:
            # Extract field value based on position
            start, end = field['position']
            if end < 0:  # Handle negative indices (take to the end)
                end = len(line) + end + 1
                
            if len(line) < start:
                # Line too short, use default if available
                value = field.get('default', '')
            elif len(line) < end:
                # Line shorter than expected end, but we can still extract partial value
                value = line[start:]
            else:
                value = line[start:end]
            
            # Convert the value based on type
            field_type = field.get('type', 'string')
            
            if field_type == 'special' and 'parser' in field:
                # Handle special parser for complex formats
                parser_name = field['parser']
                if parser_name in self.special_parsers_dict:
                    parsed_data = self.special_parsers_dict[parser_name](value)
                    # Merge parsed results into the overall result
                    if isinstance(parsed_data, dict):
                        result.update(parsed_data)
                    continue
                    
            elif field_type == 'boolean' and 'mapping' in field:
                value = self.type_converters[field_type](value, field['mapping'])
            elif field_type == 'date' and 'format' in field:
                value = self.type_converters[field_type](value, field['format'])
            elif field_type in self.type_converters:
                value = self.type_converters[field_type](value)
                
            # Apply transforms if specified
            transform_name = field.get('transform')
            if transform_name and transform_name in self.transforms:
                value = self.transforms[transform_name](value)
                
            # Store the result
            result[field['name']] = value
            
        return result


class JSCYConfigParser:
    """
    JSCY-specific implementation of the config-driven parser
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with optional custom config path
        
        Args:
            config_path: Path to custom YAML config, uses default if None
        """
        # Use default config if not specified
        if config_path is None:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(base_path, 'src', 'config', 'jscy_format.yaml')
            
        self.parser = ConfigParser(config_path)
    
    def parse_jscy_content(self, content: str) -> List[Dict[str, Any]]:
        """
        Parse JSCY content using the configuration
        
        Args:
            content: JSCY formatted content string
            
        Returns:
            List of dictionaries with parsed flight data
        """
        return self.parser.parse_content(content)
    
    @classmethod
    def get_parser(cls, config_path: Optional[str] = None) -> 'JSCYConfigParser':
        """
        Factory method to get a parser instance
        
        Args:
            config_path: Optional custom config path
            
        Returns:
            JSCYConfigParser instance
        """
        return cls(config_path)
        
    @staticmethod
    def parse_jscy_file(content: str) -> List[Dict[str, Any]]:
        """
        Static method for direct parsing without creating an instance
        
        Args:
            content: JSCY formatted content string
            
        Returns:
            List of dictionaries with parsed flight data
        """
        parser = JSCYConfigParser.get_parser()
        return parser.parse_jscy_content(content) 