function doPost(e) {
  try {
    // Parse the incoming JSON payload from the ESP32
    var data = JSON.parse(e.postData.contents);
    
    var player = data.player;
    var durationMinutes = data.durationMinutes;
    var timestamp = new Date();
    
    // Get the active sheet (make sure you are bound to a Google Sheet)
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    
    // Add the data as a new row
    sheet.appendRow([timestamp, player, durationMinutes]);
    
    // Return a success response
    return ContentService.createTextOutput(JSON.stringify({"status": "success"}))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    // Return an error response
    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": error.message}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
