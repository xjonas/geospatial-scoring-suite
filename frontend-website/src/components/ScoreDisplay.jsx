import { scoreInfo, getScoreRange } from '../constants/scoreInfo';

const ScoreDisplay = ({ scores, city }) => {
  if (!scores || Object.keys(scores).length === 0) {
    return null;
  }

  // Get array of score entries
  const scoreEntries = Object.entries(scores);

  return (
    <div className="mt-8">
      <h2 className="text-2xl font-bold mb-6 text-center">
        Location Scores für den Punkt in {city ? `${city}` : 'Location'}:
      </h2>
      <p className="text-center text-gray-600">
        Für eine einfache Vergleichbarkeit erhölt jeder Punkt eine Bewertung von 0 bis 100, wobei 0 die schlechteste und 100 die beste Bewertung ist.
        <br />
        Alle Berechnungen basieren dabei auf offiziellen Daten und Statistiken, sowie proprietären Modellen. 
      </p>
      
      <div className="score-display-container">
        {scoreEntries.map(([metric, value]) => {
          if (!scoreInfo[metric]) return null;

          // Use title and description directly from scoreInfo and getScoreRange
          const { title, description: metricDescription } = scoreInfo[metric]; // Renamed description to avoid conflict
          const { label, description: rangeDescription } = getScoreRange(metric, value);

          // Determine color class based on score value
          const getScoreColorClass = (value) => {
            if (value > 80) return 'score-bubble-excellent';
            else if (value > 60) return 'score-bubble-good';
            else if (value > 30) return 'score-bubble-moderate';
            else return 'score-bubble-poor';
          };

          const scoreColorClass = getScoreColorClass(value);

          return (
            <div key={metric} className="score-card">
              <div className="card-header">
                {/* Card title - Use title from scoreInfo */}
                <h3 className="font-bold text-xl">{title}</h3>
                {/* Metric Description - Use description from scoreInfo */}
                <p className="text-sm text-gray-600">{metricDescription}</p>
              </div>

              {/* Score display with improved styling */}
              <div className="score-bubble-container">
                <div className={`score-bubble ${scoreColorClass}`}>
                  <span className="score-value">{value}</span>
                  <span className="score-max">/100</span>
                </div>
              </div>

              {/* Description - Use label and rangeDescription from getScoreRange */}
              <div className="card-footer">
                <p className="text-sm text-center text-gray-700">
                  <span className="font-medium">{label}:</span> {rangeDescription}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ScoreDisplay;