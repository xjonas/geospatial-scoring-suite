
class APITracker:
    # Simplified API call tracker that works by monkey patching the requests module
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(APITracker, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Initialize the tracker and monkey patch requests
        self.call_counts = {
            'openmeteo': {'best': 0, 'realistic': 0, 'worst': 0},
            'osm': 0
        }

        # Start tracking by monkey patching requests
        self._patch_requests()

    def _patch_requests(self):
        # Patch the requests module to intercept API calls
        import requests
        original_get = requests.get

        def patched_get(url, *args, **kwargs):
            # Track the API call before making it
            if 'open-meteo.com' in url:
                self._track_openmeteo(url, kwargs.get('params', {}))
            elif 'overpass-api.de' in url or 'nominatim.openstreetmap.org' in url:
                self._track_osm(url)

            # Call the original function
            return original_get(url, *args, **kwargs)

        # Replace the original function
        requests.get = patched_get

    def _track_openmeteo(self, url, params):
        # Track an Open-Meteo API call
        # Define costs for each scenario
        if 'air-quality' in url:
            costs = {'best': 16, 'realistic': 16, 'worst': 27}  # Pollution
        elif 'elevation' in url:
            costs = {'best': 1, 'realistic': 11, 'worst': 95}   # Elevation
        elif 'climate' in url or '/v1/forecast' in url:
            costs = {'best': 57, 'realistic': 57, 'worst': 288} # Climate

        # Add costs to all scenarios
        for scenario in ['best', 'realistic', 'worst']:
            self.call_counts['openmeteo'][scenario] += costs[scenario]

        print(f"Open-Meteo API call tracked - Best: {costs['best']:.2f}, "
              f"Realistic: {costs['realistic']:.2f}, Worst: {costs['worst']:.2f}")

    def _track_osm(self, url):
        # Track an OSM API call
        self.call_counts['osm'] += 1
        print(f"OSM API call tracked")

    def get_summary(self):
        # Get a simple summary of API usage
        # Different scenarios because usage depends on the data requested, which is not always 100% known 
        summary = "\nSummary:\n"
        summary += "Open-Meteo API calls:\n"
        summary += f"Best case: {self.call_counts['openmeteo']['best']:.2f}\n"
        summary += f"Realistic case: {self.call_counts['openmeteo']['realistic']:.2f}\n"
        summary += f"Worst case: {self.call_counts['openmeteo']['worst']:.2f}\n"
        summary += f"OSM API calls: {self.call_counts['osm']}\n"
        total_best = self.call_counts['openmeteo']['best'] + self.call_counts['osm']
        total_real = self.call_counts['openmeteo']['realistic'] + self.call_counts['osm']
        total_worst = self.call_counts['openmeteo']['worst'] + self.call_counts['osm']
        summary += "Total API calls:\n"
        summary += f"Best case: {total_best:.2f}\n"
        summary += f"Realistic case: {total_real:.2f}\n"
        summary += f"Worst case: {total_worst:.2f}\n"
        return summary

    def print_summary(self):
        print(self.get_summary())