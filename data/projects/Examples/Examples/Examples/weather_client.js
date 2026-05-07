/**
 * JavaScript Client for Sapo Weather JSON API
 * Fetches and parses the weather forecast for a given city code.
 */

const API_BASE_URL = "https://services.sapo.pt/WeatherJSON/GetWeatherForecast";

/**
 * Fetches the raw JSON weather forecast data from the API.
 * @param {string} cityCode - The code for the city (e.g., 'LPLG' for Lisbon).
 * @returns {Promise<Object>} A promise that resolves with the parsed JSON object.
 */
async function fetchWeatherForecast(cityCode) {
    const url = `${API_BASE_URL}?cityCode=${cityCode}`;
    console.log(`Fetching data from: ${url}`);
    
    try {
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        // Since the API returns JSON, we use response.json()
        const data = await response.json();
        return data;

    } catch (error) {
        console.error("Failed to fetch weather forecast:", error.message);
        throw error;
    }
}

/**
 * Extracts and structures the forecast data from the complex JSON object.
 * @param {Object} rawData - The full JSON object returned by the API.
 * @returns {Object} An object containing the current weather and the array of daily forecasts.
 */
function structureForecastData(rawData) {
    // The JSON structure is nested: 
    // rawData -> GetWeatherForecastResponse -> GetWeatherForecastResult
    const result = rawData?.GetWeatherForecastResponse?.GetWeatherForecastResult;

    if (!result) {
        throw new Error("Invalid or incomplete data structure received from the API.");
    }

    // Extracting the current weather details
    const currentWeather = result.CurrentWeather;

    // Extracting the array of daily forecasts
    const dailyForecasts = result.Days?.Day || [];

    return {
        current: {
            city: currentWeather.City,
            description: currentWeather.Description,
            highTemp: currentWeather.AirTemperature, // Using AirTemperature for current
            windSpeed: currentWeather.WindSpeed,
            pressure: currentWeather.BarometricPressure
        },
        forecasts: dailyForecasts.map(day => ({
            dayName: day.Name,
            description: day.Description,
            highTemp: day.High,
            lowTemp: day.Low,
            uvIndex: day.SunRaysUV
        }))
    };
}


/**
 * Main function to execute the fetch, parse, and display process.
 * @param {string} cityCode - The city code to query.
 */
async function getAndDisplayForecast(cityCode) {
    try {
        // 1. Fetch the raw JSON data
        const rawData = await fetchWeatherForecast(cityCode);
        
        // 2. Structure the data for easy use
        const structuredData = structureForecastData(rawData);
        
        // 3. Display the results
        console.log("\n=========================================");
        console.log(`☀️ Current Weather in ${structuredData.current.city}:`);
        console.log(`   Condition: ${structuredData.current.description}`);
        console.log(`   Temperature: ${structuredData.current.highTemp}°C`);
        console.log(`   Wind Speed: ${structuredData.current.windSpeed} km/h`);
        console.log("=========================================\n");

        console.log("🗓️ Upcoming Forecast:");
        structuredData.forecasts.forEach(day => {
            console.log(`- ${day.dayName}: ${day.description} | High: ${day.highTemp}°C | Low: ${day.lowTemp}°C | UV: ${day.uvIndex}`);
        });

    } catch (error) {
        console.error("\n--- Error ---");
        console.error("Could not complete the weather forecast retrieval or parsing:", error.message);
    }
}

// --- Execution Example ---
// To run the client for Lisbon (LPLG), uncomment the line below:
getAndDisplayForecast('LPLG');