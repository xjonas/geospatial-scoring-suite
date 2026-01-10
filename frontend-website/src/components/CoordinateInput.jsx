import { useState } from 'react';

const CoordinateInput = ({ onSubmit, isLoading }) => {
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    // Basic validation or use default values
    const lat = latitude.trim() === '' ? '50.1189' : latitude;
    const lon = longitude.trim() === '' ? '9.8949' : longitude;
    onSubmit({ latitude: lat, longitude: lon });
  };

  return (
    // Added position: relative and z-index: 1 to ensure it's above the background pseudo-element
    <div className="card relative z-10">
      {/* Increased vertical spacing with space-y-8 */}
      <form onSubmit={handleSubmit} className="flex flex-col items-center space-y-8">
        {/* Explicit width w-64 */}
        <input
          id="latitude"
          type="number"
          step="any"
          value={latitude} // Ensure value is bound
          onChange={(e) => setLatitude(e.target.value)} // Ensure onChange updates state
          placeholder="Breitengrad z.B 50.00"
          className="input-field w-64" // Use fixed width instead of max-w
          required
        />
        {/* Explicit width w-64 */}
        <input
          id="longitude"
          type="number"
          step="any"
          value={longitude} // Ensure value is bound
          onChange={(e) => setLongitude(e.target.value)} // Ensure onChange updates state
          placeholder="Längengrad z.B 9.00"
          className="input-field w-64" // Use fixed width instead of max-w
          required
        />
        {/* Increased top margin mt-12 */}
        <button
          type="submit"
          disabled={isLoading}
          className="btn-primary w-64 mt-12" // Match input width and increase margin
        >
          {isLoading ? 'Laden...' : 'Scores abrufen'}
        </button>
      </form>
    </div>
  );
};

export default CoordinateInput;