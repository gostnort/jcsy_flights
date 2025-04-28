import yaml
import re
import os
from typing import Dict, Any, List, Callable
from concurrent.futures import ThreadPoolExecutor



class JcsyParser:
    """
    Manages calling different configuration files for different JCSY formats
    """
    

    def __init__(self, config_file: str):
        """
        Args:
            config_file: Name of the YAML config file located in the "src/config" folder
        """
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(base_path, 'bin', 'config', config_file)
        self.config = self._load_config(config_path)
        self.transforms = self._prepare_transforms()
        self.type_converters = self._prepare_type_converters()
        self.special_parsers = self._prepare_special_parsers()
    

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:    
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise FileNotFoundError(f"Error: The configuration file not found at {config_path}.\n {e}")


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
    
    
    def parse_content(self, content: str) -> Dict[str, Dict[str, Any]]:
        """
        Parse content string according to configuration with parallel processing
        Returns a dictionary where keys are pattern types and values are dictionaries of field->value
        """
        lines = content.strip().split('\n')
        # Still process header and title sequentially (these are prerequisites)
        current_header = {}
        context = {}
        flight_lines = []
        # First pass: identify all line types and process header/title
        for line in lines:
            line = line.rstrip()
            if len(line) < 12:
                continue
            header_pattern = self.config.get('header', {}).get('pattern')
            if header_pattern and re.match(header_pattern, line):
                current_header = self._parse_line(line, 'header')
                continue
            
            title_pattern = self.config.get('title_line', {}).get('pattern')
            if title_pattern and re.match(title_pattern, line):
                context = self._parse_line(line, 'title_line')
                continue
            
            flight_pattern = self.config.get('flight', {}).get('pattern')
            if flight_pattern and re.match(flight_pattern, line):
                flight_lines.append(line)
                
        # Process flight lines in parallel
        flight_data = {}
        if flight_lines:
            with ThreadPoolExecutor() as executor:
                # Create tasks for parallel processing
                futures = [
                    executor.submit(self._process_flight_line, line, current_header, context) 
                    for line in flight_lines
                ] 
                # Collect results as they complete
                for i, future in enumerate(futures):
                    result = future.result()
                    # Each flight gets its own dictionary in the flight_data
                    flight_data[f"flight_{i}"] = result
                    
        # Return organized results matching the sample structure
        results = {
            'header': current_header,
            'title_line': context,
            'flight': flight_data
        }
        return results
    
    def _process_flight_line(self, line, header, context):
        """Helper method to process a flight line with its context"""
        flight_data = self._parse_line(line, 'flight', context)
        return {**header, **flight_data, 'line': line}
    

    def _parse_line(self, line: str, line_type: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Parse a single line according to configuration
        Args:
            line: The line to parse
            line_type: Type of line (header, title_line, flight)
            context: Contextual data from previous parsing
        Returns:
            Dictionary containing parsed data
        """
        if context is None:
            context = {}
        result = {}
        line_config = self.config.get(line_type, {})
        # Header lines use regex with named capture groups
        if line_type == 'header':
            match = re.match(line_config.get('pattern', ''), line)
            if match:
                result = match.groupdict()
                # Apply transforms to specific fields
                transforms = line_config.get('transforms', {})
                for field, transform in transforms.items():
                    if field in result:
                        if transform.startswith('lambda'):
                            transform_fn = eval(transform)
                            result[field] = transform_fn(result[field])
                        elif transform in self.special_parsers:
                            result[field] = self.special_parsers[transform](result[field])
                        elif transform in self.transforms:
                            result[field] = self.transforms[transform](result[field])
        # Title lines extract positions
        elif line_type == 'title_line':
            extract_positions = line_config.get('extract_positions', {})
            for pos_name, pos_fn in extract_positions.items():
                if pos_fn.startswith('lambda'):
                    fn = eval(pos_fn)
                    result[pos_name] = fn(line)
        # Flight lines are pre-processed and then parsed by section
        elif line_type == 'flight':
            # Pre-process the line using the context
            if 'pre_process' in line_config:
                pre_process_fn = eval(line_config['pre_process'])
                sections = pre_process_fn(line, context)
                # Parse flight info section (position-based)
                flight_info = sections.get('flight_info', '')
                flight_info_config = line_config.get('flight_info', {})
                for field_name, pos in flight_info_config.items():
                    start, end = pos
                    if end == -1:
                        result[field_name] = flight_info[start:].strip()
                    else:
                        result[field_name] = flight_info[start:end].strip()
                
                # Special handling for std field with timezone conversion
                if 'std' in result and result['std']:
                    header_date = context.get('header', {}).get('header_flight_date', '')
                    airport = result.get('airport', '')
                    if header_date and airport:
                        result['std'] = self.special_parsers['parse_std_time'](
                            result['std'], 
                            header_date,
                            airport
                        )
                
                # Parse counts section (split and index-based)
                counts = sections.get('counts', '')
                counts_config = line_config.get('counts', {})
                split_pattern = counts_config.get('split', '\\s+')
                count_parts = re.split(split_pattern, counts)
                # Process each field in the counts section
                for field_name, field_config in counts_config.get('fields', {}).items():
                    idx = field_config.get('index', 0)
                    if 0 <= idx < len(count_parts):
                        field_value = count_parts[idx]
                        # If further splitting is needed
                        if 'split' in field_config:
                            sub_parts = re.split(field_config['split'], field_value)
                            field_names = field_config.get('fields', [])
                            transforms = field_config.get('transforms', {})
                            # Map split values to field names
                            for i, sub_field in enumerate(field_names):
                                if i < len(sub_parts):
                                    # Get the value and apply transforms
                                    val = sub_parts[i].strip()
                                    # Apply transform if specified
                                    if sub_field in transforms and transforms[sub_field] in self.transforms:
                                        val = self.transforms[transforms[sub_field]](val)
                                    # Convert to integer for count fields
                                    if sub_field.endswith('count') or sub_field.endswith('piece') or sub_field.endswith('weight'):
                                        try:
                                            val = int(val) if val else 0
                                        except ValueError:
                                            pass
                                    result[sub_field] = val
        return result
    