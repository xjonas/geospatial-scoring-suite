import { useState } from 'react';
import CoordinateInput from './components/CoordinateInput';
import ScoreDisplay from './components/ScoreDisplay';
import LoadingIndicator from './components/LoadingIndicator';
import { fetchLocationScores } from './utils/api';
import NeighborhoodMap from './components/NeighborhoodMap';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [locationData, setLocationData] = useState(null);
  const [showNotification, setShowNotification] = useState(true);

  const handleSubmit = async (coordinates) => {
    setError('');
    setIsLoading(true);
    
    try {
      const data = await fetchLocationScores(coordinates.latitude, coordinates.longitude);
      setLocationData(data);
    } catch (err) {
      let errorMessage;
      if (err.message === 'LOCATION_NOT_FOUND') {
        errorMessage = 'Diese Location ist noch nicht verfügbar. Bitte versuchen Sie es mit einer anderen.';
      } else if (err.message === 'SERVER_LIMIT') {
        errorMessage = 'Unsere Server sind am Limit! Bitte versuchen Sie es später erneut.'; // Updated message for 429
      } else {
        // Generic fallback for API_ERROR or other unexpected errors
        errorMessage = 'Ein unerwarteter Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.';
        console.error("Error during fetch:", err); // Log the actual error object
      }
      setError(errorMessage);
      setLocationData(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center font-epilogue relative">
      <div className="container mx-auto px-4 py-12 max-w-4xl text-center mb-[10rem]">
        <header className="mb-10">
          <h1 className="text-5xl font-bold mb-5">Das #1 Location Scoring in Deutschland!</h1>
          <p className="text-gray-700 text-lg font-light max-w-3xl mx-auto">
            Wie resistant ist Ihr Grundstück gegen Dürre? Wie sicher Ihre Nachbarschaft?
            <br></br>
            Wie gut ist die Umgebung zu Fuß begehbar? Wie gut ist die Luftqualität im Vergleich?
          </p>
          <h3 className="text-xl font-bold mt-10 mb-10">Jetzt kostenlos bewerten lassen!</h3>
        </header>

        {/* Beta Test Notification Panel - only visible when scores aren't loaded */}
        {!locationData && !isLoading && showNotification && (
          <div className="beta-notification relative">
            <button 
              onClick={() => setShowNotification(false)}
              className="beta-notification-close"
              aria-label="Close notification"
            >
              ✕
            </button>
            <p>! Beta Testphase !</p>
            <p>Verfügbare Städte:</p>
            <ul>
              <li> Kiel</li>
              <li> München</li>
              <li> Karlsruhe</li>
              <li> Würzburg</li>
            </ul>
          </div>
        )}

        <div className="max-w-md mx-auto mb-8 ">
          <CoordinateInput onSubmit={handleSubmit} isLoading={isLoading} />
        </div>
        
        {isLoading && <LoadingIndicator />}
        
        {error && (
          <div className="error-message"> {/* Use the dedicated CSS class */}
            <p>{error}</p>
          </div>
        )}
        
        {!isLoading && !error && locationData && (
          <>
            <ScoreDisplay 
              scores={locationData.scores} 
              city={locationData.city_name} 
              country={locationData.country} 
            />
            <NeighborhoodMap 
              centerLat={locationData.latitude}
              centerLng={locationData.longitude}
              city={locationData.city_name}
            />
          </>
        )}
      </div>
      
      <div className="logo-container flex flex-row items-center gap-[20px] bg-white/80 rounded-md px-4 py-2">
        <p className="text-gray-500 text-sm">powered by</p>
        <a href="https://neivo.de" target="_blank" rel="noopener noreferrer">
          <img src="/neivo-banner-2.png" alt="Neivo Logo" className="w-[200px] h-[75px]" />
        </a>
      </div>
    </div>
  );
}

export default App;