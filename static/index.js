function get_listings(clear, count) {
  var count = count || 5
  var current = clear? 0 : $('.listing').length;
  var prices = $('#price_slider').slider('option', 'values');
  var times = $('#time_slider').slider('option', 'values')
  $.ajax({
    url: 'listings',
    dataType: 'json',
    async: false,
    data: {
      price_lower: prices[0],
      price_upper: prices[1],
      time_lower: times[0],
      time_upper: times[1],
      index_lower: current,
      index_upper: current + count},
    success: function (listings) {
      if (clear) {
        $('.listings').empty();
      }

      var template = $('#listing-template').html();
      Mustache.parse(template);
      $.each(listings, function (index, listing) {
        var rendered = Mustache.render(template, listing)
        $('.listings').append(rendered);
      });
    }
  });
}

function set_slider_handles(name) {
  var values = $(name).slider('option', 'values');
  var handles = $(name + ' .ui-slider-handle')
  $(handles[0]).text(values[0])
  $(handles[1]).text(values[1])
}

$(function () {
 $('#price_slider').slider({
   range: true,
   min: 500,
   max: 2000,
   step: 100,
   values: [500, 2000],
   create: function () { set_slider_handles('#price_slider'); },
   slide: function (e, ui) {
     set_slider_handles('#price_slider');
     get_listings(true);
   }
 });
});



$(function () {
 $('#time_slider').slider({
   range: true,
   min: 0,
   max: 30,
   step: 1,
   values: [0, 30],
   create: function () { set_slider_handles('#time_slider'); },
   slide: function (e, ui) {
     set_slider_handles('#time_slider');
     get_listings(true); }
 });
});


$(window).on('scroll', function() {
    if( $(window).scrollTop() > $(document).height() - $(window).height() - 600 ) {
        get_listings(false);
    }
});

$('document').ready(function () { get_listings(true); });
