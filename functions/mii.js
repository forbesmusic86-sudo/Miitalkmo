// functions/mii.js
/**
 * Miitalkmo Mii Image Proxy
 * Proxies requests to Nintendo Mii Studio API with caching
 * Supports custom Mii data generation and image rendering
 */

export async function onRequest(context) {
	const cache = caches.default;
	const nurl = new URL(context.request.url);
	const path = nurl.pathname;

	// Check cache first
	let cresponse = await cache.match(context.request);
	if (cresponse) {
		return new Response(cresponse.body, {
			status: cresponse.status,
			headers: cresponse.headers,
		});
	}

	// Route: /mii -> Nintendo Mii Studio
	if (path === "/mii" || path === "/mii/") {
		return handleMiiImageRequest(context, cache);
	}

	// Route: /mii/data -> Parse Mii data
	if (path === "/mii/data" || path === "/mii/data/") {
		return handleMiiDataRequest(context);
	}

	// Route: /mii/list -> List available Miis
	if (path === "/mii/list" || path === "/mii/list/") {
		return handleMiiListRequest(context);
	}

	return new Response("Not found", { status: 404 });
}

/**
 * Handle Mii image generation requests
 * Proxies to Nintendo Mii Studio with caching
 */
async function handleMiiImageRequest(context, cache) {
	const nurl = new URL(context.request.url);
	const requestUrl = new URL("https://studio.mii.nintendo.com/miis/image.png");

	// Forward all query parameters
	for (const [key, value] of nurl.searchParams.entries()) {
		requestUrl.searchParams.set(key, value);
	}

	const request = new Request(requestUrl, {
		method: context.request.method,
		headers: {
			"User-Agent": "Miitalkmo/1.0",
			...Object.fromEntries(context.request.headers),
		},
		body: context.request.body,
	});

	try {
		const response = await fetch(request);

		// Only cache successful responses
		if (response.ok) {
			const finalResponse = new Response(response.body, {
				status: response.status,
				headers: response.headers,
			});

			// Set cache headers
			finalResponse.headers.set("Cache-Control", "max-age=604800, public");
			finalResponse.headers.set("Content-Type", "image/png");
			finalResponse.headers.set("Access-Control-Allow-Origin", "*");

			// Store in cache
			await cache.put(context.request, finalResponse.clone());

			return finalResponse;
		}

		return new Response("Mii Studio error", { status: response.status });
	} catch (error) {
		console.error("Mii image request error:", error);
		return new Response("Error fetching Mii image", { status: 500 });
	}
}

/**
 * Handle Mii data parsing
 * Converts Mii data format and returns metadata
 */
async function handleMiiDataRequest(context) {
	const nurl = new URL(context.request.url);
	const miiData = nurl.searchParams.get("data");
	const format = nurl.searchParams.get("format") || "json";

	if (!miiData) {
		return new Response(
			JSON.stringify({ error: "Mii data parameter required" }),
			{
				status: 400,
				headers: {
					"Content-Type": "application/json",
					"Access-Control-Allow-Origin": "*",
				},
			}
		);
	}

	try {
		const parsed = parseMiiData(miiData);

		return new Response(JSON.stringify(parsed), {
			status: 200,
			headers: {
				"Content-Type": "application/json",
				"Cache-Control": "max-age=3600, public",
				"Access-Control-Allow-Origin": "*",
			},
		});
	} catch (error) {
		return new Response(
			JSON.stringify({ error: `Failed to parse Mii data: ${error}` }),
			{
				status: 400,
				headers: {
					"Content-Type": "application/json",
					"Access-Control-Allow-Origin": "*",
				},
			}
		);
	}
}

/**
 * Handle Mii list request
 * Returns available Miis from local storage/database
 */
async function handleMiiListRequest(context) {
	try {
		// Fetch from KV storage if available
		const miis = await context.env.MII_DATA?.get("miis", "json") || [];

		return new Response(JSON.stringify({ miis }), {
			status: 200,
			headers: {
				"Content-Type": "application/json",
				"Cache-Control": "max-age=300, public",
				"Access-Control-Allow-Origin": "*",
			},
		});
	} catch (error) {
		return new Response(
			JSON.stringify({ error: `Failed to fetch Mii list: ${error}` }),
			{
				status: 500,
				headers: {
					"Content-Type": "application/json",
					"Access-Control-Allow-Origin": "*",
				},
			}
		);
	}
}

/**
 * Parse Mii data from hex or base64 format
 * Extracts name, appearance, and voice settings
 */
function parseMiiData(data) {
	// Convert hex to bytes
	let bytes;
	if (data.length % 2 === 0 && /^[0-9a-f]+$/i.test(data)) {
		bytes = hexToBytes(data);
	} else {
		bytes = base64ToBytes(data);
	}

	if (!bytes || bytes.length < 0x60) {
		throw new Error("Invalid Mii data format");
	}

	// Parse Mii structure (simplified)
	const name = extractMiiName(bytes);
	const appearance = extractMiiAppearance(bytes);
	const voice = extractMiiVoice(bytes);

	return {
		name,
		appearance,
		voice,
		dataSize: bytes.length,
		format: "ver3_studio",
	};
}

/**
 * Extract Mii name from data
 */
function extractMiiName(bytes) {
	// Mii names are typically at offset 0x08, UTF-16LE encoded
	const nameBytes = bytes.slice(0x08, 0x1c);
	const name = new TextDecoder("utf-16le").decode(nameBytes).split("\0")[0];
	return name || "Unnamed";
}

/**
 * Extract Mii appearance data
 */
function extractMiiAppearance(bytes) {
	return {
		faceShape: bytes[0x04] & 0x07,
		skinColor: (bytes[0x04] >> 3) & 0x07,
		eyeType: bytes[0x0c] & 0x3f,
		eyeColor: (bytes[0x0d] >> 4) & 0x07,
		mouthType: bytes[0x12] & 0x3f,
	};
}

/**
 * Extract Mii voice settings (Miitomo style: 5 parameters)
 */
function extractMiiVoice(bytes) {
	// Voice data typically starts around offset 0x10A in Tomodachi Life
	const voiceOffset = 0x10a;

	if (bytes.length < voiceOffset + 6) {
		return null;
	}

	return {
		pitch: bytes[voiceOffset],
		speed: bytes[voiceOffset + 1],
		quality: bytes[voiceOffset + 2],
		tone: bytes[voiceOffset + 3],
		accent: bytes[voiceOffset + 4],
		intonation: bytes[voiceOffset + 5],
	};
}

/**
 * Convert hex string to byte array
 */
function hexToBytes(hex) {
	const bytes = [];
	for (let i = 0; i < hex.length; i += 2) {
		bytes.push(parseInt(hex.substr(i, 2), 16));
	}
	return new Uint8Array(bytes);
}

/**
 * Convert base64 string to byte array
 */
function base64ToBytes(base64) {
	const binary = atob(base64);
	const bytes = [];
	for (let i = 0; i < binary.length; i++) {
		bytes.push(binary.charCodeAt(i));
	}
	return new Uint8Array(bytes);
    }
