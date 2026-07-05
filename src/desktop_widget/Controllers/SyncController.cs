using Microsoft.AspNetCore.Mvc;
using System.Net.Http;
using System.Threading.Tasks;

namespace DesktopWidget.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class SyncController : ControllerBase
    {
        private readonly HttpClient _httpClient;

        public SyncController()
        {
            _httpClient = new HttpClient();
        }

        [HttpGet("valuation")]
        public async Task<IActionResult> GetValuation()
        {
            // Proxy request to Python backend
            var response = await _httpClient.GetAsync("http://localhost:8000/api/valuation");
            if (response.IsSuccessStatusCode)
            {
                var content = await response.Content.ReadAsStringAsync();
                return Ok(content);
            }
            return StatusCode((int)response.StatusCode, "Error fetching from backend");
        }
    }
}
