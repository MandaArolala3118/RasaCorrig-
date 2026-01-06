
        /// <summary>
        /// Envoyer un message à Rasa
        /// </summary>
        [HttpPost("message")]
        [ProducesResponseType(typeof(List<RasaResponse>), 200)]
        [ProducesResponseType(400)]
        [ProducesResponseType(500)]
        public async Task<ActionResult<List<RasaResponse>>> SendMessage(
            [FromForm] string sender,
            [FromForm] string text,
            [FromForm] List<IFormFile> files = null)
        {
            if (string.IsNullOrWhiteSpace(sender))
            {
                return BadRequest(new { error = "Le paramètre 'sender' est requis" });
            }

            if (string.IsNullOrWhiteSpace(text))
            {
                return BadRequest(new { error = "Le paramètre 'text' est requis" });
            }

            try
            {
                var responses = await _rasaService.SendMessageAsync(sender, text, files);
                return Ok(responses);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Erreur lors de l'envoi du message à Rasa");
                return StatusCode(500, new { error = "Erreur lors de l'envoi du message", details = ex.Message });
            }
        }