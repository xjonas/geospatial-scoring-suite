/**
 * Information about each score type including titles, descriptions and range interpretations
 */
export const scoreInfo = {
    walkability: {
      title: "Walkability",
      description: "Fußgängerfreundlichkeit der Umgebung",
      ranges: [
        { min: 0, max: 30, label: "Schlecht", description: "Autoabhängige Gegend mit minimaler Fußgängerinfrastruktur" },
        { min: 31, max: 60, label: "Mäßig", description: "Einige Annehmlichkeiten zu Fuß erreichbar, aber begrenzte Infrastruktur" },
        { min: 61, max: 80, label: "Gut", description: "Viele Ziele zu Fuß erreichbar mit guter Infrastruktur" },
        { min: 81, max: 100, label: "Exzellent", description: "Sehr fußgängerfreundlich mit hervorragendem Zugang zu Annehmlichkeiten" }
      ]
    },
    healthcare_access: {
      title: "Gesundheitsversorgung",
      description: "Zugang zu Gesundheitsdiensten in der Umgebung",
      ranges: [
        { min: 0, max: 30, label: "Schlecht", description: "Begrenzte Gesundheitseinrichtungen mit schwierigem Zugang" },
        { min: 31, max: 60, label: "Mäßig", description: "Grundlegende Gesundheitsdienste verfügbar, erfordern aber möglicherweise Reisen" },
        { min: 61, max: 80, label: "Gut", description: "Gute Auswahl an Gesundheitsoptionen in angemessener Entfernung" },
        { min: 81, max: 100, label: "Exzellent", description: "Umfassende Gesundheitsdienste leicht zugänglich" }
      ]
    },
    green_space_access: {
      title: "Grünflächen",
      description: "Zugang zu Parks und Erholungsgebieten in unmittelbarer Nähe",
      ranges: [
        { min: 0, max: 30, label: "Schlecht", description: "Wenig Grünflächen in der Nähe oder nicht zugänglich" },
        { min: 31, max: 60, label: "Mäßig", description: "Einige Grünflächen verfügbar, aber möglicherweise schlecht zugänglich" },
        { min: 61, max: 80, label: "Gut", description: "Gute Verfügbarkeit von Parks und Erholungsgebieten" },
        { min: 81, max: 100, label: "Exzellent", description: "Reichlich Grünflächen und Parks in unmittelbarer Nähe" }
      ]
    },
    poi_access_overall: {
      title: "Point of Interests",
      description: "Zugang zu wichtigen Annehmlichkeiten wie Geschäften und Restaurants",
      ranges: [
        { min: 0, max: 30, label: "Schlecht", description: "Begrenzter Zugang zu Annehmlichkeiten, erfordert weite Reisen" },
        { min: 31, max: 60, label: "Mäßig", description: "Einige Annehmlichkeiten in der Nähe, aber nicht optimal erreichbar" },
        { min: 61, max: 80, label: "Gut", description: "Gute Verfügbarkeit von Annehmlichkeiten in der Umgebung" },
        { min: 81, max: 100, label: "Exzellent", description: "Reichlich Annehmlichkeiten in unmittelbarer Nähe" }
      ]
    },
    crime_safety_living: {
      title: "Sicherheit",
      description: "Sicherheitsniveau basierend auf Kriminalitätsraten",
      ranges: [
        { min: 0, max: 30, label: "Schlecht", description: "Höhere Kriminalitätsraten mit erheblichen Sicherheitsbedenken" },
        { min: 31, max: 60, label: "Mäßig", description: "Durchschnittliche Kriminalitätsraten mit einigen Sicherheitsaspekten" },
        { min: 61, max: 80, label: "Gut", description: "Niedrigere als durchschnittliche Kriminalitätsraten, generell sicher" },
        { min: 81, max: 100, label: "Exzellent", description: "Sehr niedrige Kriminalitätsraten, sehr sichere Gegend" }
      ]
    },
    air_quality: {
      title: "Luftqualität",
      description: "Luftverschmutzungsniveau in der Umgebung",
      ranges: [
        { min: 0, max: 30, label: "Schlecht", description: "Hohe Schadstoffbelastung, potenzielle Gesundheitsbedenken" },
        { min: 31, max: 60, label: "Mäßig", description: "Mäßige Luftqualität mit gelegentlichen Schadstoffproblemen" },
        { min: 61, max: 80, label: "Gut", description: "Generell saubere Luft mit wenigen Schadstoffproblemen" },
        { min: 81, max: 100, label: "Exzellent", description: "Sehr saubere Luft mit minimaler Verschmutzung" }
      ]
    },
    noise_pollution: {
      title: "Lärmbelästigung",
      description: "Lärmpegel in der Umgebung",
      ranges: [
        { min: 0, max: 30, label: "Hoch", description: "Sehr laute Umgebung mit häufigen Störungen" },
        { min: 31, max: 60, label: "Mäßig", description: "Einige Lärmprobleme, aber generell beherrschbar" },
        { min: 61, max: 80, label: "Niedrig", description: "Relativ ruhig mit gelegentlichen Lärmstörungen" },
        { min: 81, max: 100, label: "Sehr niedrig", description: "Ruhige Umgebung mit minimaler Lärmbelästigung" }
      ]
    },
    climate_change_resilience: {
      title: "Klimawandelresilienz",
      description: "Widerstandsfähigkeit gegenüber den Auswirkungen des Klimawandels",
      ranges: [
        { min: 0, max: 30, label: "Niedrig", description: "Sehr anfällig für die Auswirkungen des Klimawandels" },
        { min: 31, max: 60, label: "Mäßig", description: "Einige Anfälligkeiten gegenüber den Auswirkungen des Klimawandels" },
        { min: 61, max: 80, label: "Gut", description: "Angemessen auf die Herausforderungen des Klimawandels vorbereitet" },
        { min: 81, max: 100, label: "Exzellent", description: "Gut vorbereitet und widerstandsfähig gegenüber den Auswirkungen des Klimawandels" }
      ]
    },
    drought_resistance: {
      title: "Dürreresistenz",
      description: "Widerstandsfähigkeit gegenüber Dürrebedingungen",
      ranges: [
        { min: 0, max: 30, label: "Niedrig", description: "Sehr anfällig für Dürrebedingungen" },
        { min: 31, max: 60, label: "Mäßig", description: "Einige Anfälligkeit für längere Dürreperioden" },
        { min: 61, max: 80, label: "Gut", description: "Relativ widerstandsfähig gegenüber typischen Dürrebedingungen" },
        { min: 81, max: 100, label: "Exzellent", description: "Gut auf Dürre vorbereitet mit starkem Wassermanagement" }
      ]
    }
  };
  
  /**
   * Function to get the range description based on score
   * @param {string} metric - The metric key
   * @param {number} value - The score value
   * @returns {Object} - The matching range object
   */
  export const getScoreRange = (metric, value) => {
    const ranges = scoreInfo[metric]?.ranges || [];
    return ranges.find(range => value >= range.min && value <= range.max) || {};
  };