using Microsoft.AspNetCore.Mvc;

namespace DesktopWidget.Controllers
{
    public class HomeController : Controller
    {
        public IActionResult Index()
        {
            return View();
        }
    }
}
