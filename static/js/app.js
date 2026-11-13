/*
 * app.js: comportamiento propio de la interfaz (modal de confirmación e
 * inicio de DataTables).
 *
 * Se carga después de js/sb-admin-2.min.js. Nunca calcula valores
 * financieros: solo muestra lo que el servidor ya calculó.
 */
(function ($) {
  "use strict";

  // Lee un objeto entregado por el servidor con json_script.
  function readServerJSON(elementId) {
    var element = document.getElementById(elementId);
    if (!element) {
      return {};
    }
    try {
      return JSON.parse(element.textContent);
    } catch (error) {
      return {};
    }
  }

  // DataTables: ordena, busca y pagina las filas que ya vienen en la tabla.
  // Los textos en español llegan del servidor (id "datatables-i18n").
  function initDataTables() {
    var $tables = $("table[data-datatable]");
    if (!$tables.length || !$.fn.DataTable) {
      return;
    }
    var language = readServerJSON("datatables-i18n");
    $tables.each(function () {
      $(this).DataTable({ language: language });
    });
  }

  // Modal de confirmación: cualquier form[data-confirm] lo abre antes de
  // enviarse. "Cancelar" no envía el formulario; "Confirmar" sí. Los textos
  // vienen del formulario (data-confirm, data-confirm-button) o de la
  // plantilla del modal (data-default-label).
  function initConfirmModal() {
    var $modal = $("#confirmModal");
    if (!$modal.length) {
      return;
    }
    var $message = $("#confirmModalMessage");
    var $accept = $("#confirmModalAccept");
    var pending = null; // { form, submitter } esperando respuesta

    $(document).on("submit", "form[data-confirm]", function (event) {
      var form = this;
      if (form.getAttribute("data-confirmed") === "true") {
        // Ya se confirmó: se deja seguir el envío normal.
        form.removeAttribute("data-confirmed");
        return;
      }
      event.preventDefault();
      pending = {
        form: form,
        submitter: (event.originalEvent && event.originalEvent.submitter) || null
      };
      $message.text(form.getAttribute("data-confirm"));
      $accept.text(
        form.getAttribute("data-confirm-button") || $accept.attr("data-default-label")
      );
      $modal.modal("show");
    });

    $accept.on("click", function () {
      if (!pending) {
        return;
      }
      var form = pending.form;
      var submitter = pending.submitter;
      pending = null;
      $modal.modal("hide");
      form.setAttribute("data-confirmed", "true");
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(submitter && submitter.form === form ? submitter : undefined);
      } else {
        form.submit();
      }
    });

    $modal.on("hidden.bs.modal", function () {
      pending = null;
    });
  }

  // Submenú de la página activa en pantallas pequeñas: el menú lo marca
  // abierto (`show`), y en menos de 768 px SB Admin 2 lo dibuja flotando sobre
  // el contenido. sb-admin-2.js solo lo cierra al cambiar el tamaño de la
  // ventana; aquí se cierra también al cargar, sin animación (SPEC 07).
  function closeSubmenusOnSmallScreens() {
    if ($(window).width() >= 768) {
      return;
    }
    $(".sidebar .collapse.show").each(function () {
      $(this).removeClass("show");
      $('.sidebar [data-target="#' + this.id + '"]')
        .addClass("collapsed")
        .attr("aria-expanded", "false");
    });
  }

  $(function () {
    closeSubmenusOnSmallScreens();
    initDataTables();
    initConfirmModal();
  });
})(jQuery);
