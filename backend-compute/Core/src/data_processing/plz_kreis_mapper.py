# Module for retrieving Kreis (district) information from PLZ (postal code)
import pandas as pd
import re
import os

class PLZKreisMapper:
    # Class to map PLZ codes to their corresponding Kreis (district)

    def __init__(self, csv_path):
        # Initialize the mapper with PLZ data.

        self.csv_path = csv_path
        self._plz_data = None

    @property
    def plz_data(self):
        # Lazy-load the PLZ data when first needed

        if self._plz_data is None:
            if not os.path.exists(self.csv_path):
                raise FileNotFoundError(f"PLZ data file not found: {self.csv_path}")

            # Try different parsing methods to handle CSV format issues
            try:
                # Try first with specific columns and settings to handle potential CSV issues
                df = pd.read_csv(
                    self.csv_path,
                    usecols=["Postleitzahl / Post code", "Kreis name"],
                    encoding='utf-8',
                    delimiter=',',
                    quotechar='"',
                    error_bad_lines=False, # Skip rows with parsing errors
                    warn_bad_lines=True # Warn about skipped rows
                )
            except Exception as e1:
                try:
                    # Try again with error handling options 
                    df = pd.read_csv(
                        self.csv_path,
                        usecols=["Postleitzahl / Post code", "Kreis name"],
                        encoding='utf-8',
                        delimiter=',',
                        quotechar='"',
                        on_bad_lines='skip' # New pandas option to skip bad lines
                    )
                except Exception as e2:
                    # Last resort: manually read a few lines to examine format
                    import io
                    with open(self.csv_path, 'r', encoding='utf-8') as f:
                        header = f.readline().strip()
                        # Try to detect the delimiter
                        if ';' in header:
                            delimiter = ';'
                        else:
                            delimiter = ','

                    # Try with the detected delimiter
                    df = pd.read_csv(
                        self.csv_path,
                        usecols=["Postleitzahl / Post code", "Kreis name"],
                        encoding='utf-8',
                        delimiter=delimiter,
                        quotechar='"',
                        on_bad_lines='skip'
                    )

            # Rename columns to simpler names
            df = df.rename(columns={
                "Postleitzahl / Post code": "plz",
                "Kreis name": "kreis"
            })

            # Ensure PLZ is string type
            df['plz'] = df['plz'].astype(str)

            # Store the data
            self._plz_data = df

        return self._plz_data

    def extract_kreis_name(self, kreis_string):
        # Extract the actual Kreis name from various formats

        if not kreis_string or not isinstance(kreis_string, str):
            return ""

        # Patterns to match different Kreis prefixes
        patterns = [
            r'^Kreis\s+Städteregion\s+(.+)$',  # "Kreis Städteregion Aachen"
            r'^Kreisfreie\s+Stadt\s+(.+)$',    # "Kreisfreie Stadt Düsseldorf"
            r'^Landkreis\s+(.+)$',             # "Landkreis Eifelkreis Bitburg-Prüm"
            r'^Stadtkreis\s+(.+)$',            # "Stadtkreis Stuttgart"
            r'^Kreis\s+(.+)$',                 # "Kreis Düren"
        ]

        for pattern in patterns:
            match = re.match(pattern, kreis_string)
            if match:
                return match.group(1).strip()

        # If no pattern matches, return the original string
        return kreis_string.strip()

    def get_kreis(self, plz):
        # Get the Kreis name for a given PLZ

        # Convert PLZ to string
        plz = str(plz)

        # Ensure data is loaded
        data = self.plz_data

        # Find matching row
        matching_row = data[data['plz'] == plz]

        if matching_row.empty:
            return ""

        # Get Kreis string and extract the name
        kreis_string = matching_row.iloc[0]['kreis']
        return self.extract_kreis_name(kreis_string)