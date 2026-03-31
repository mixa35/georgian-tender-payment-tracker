# HTML Response Structures

## Search Results Page HTML

```html
<!-- Pagination buttons + info (returned as part of the HTML fragment) -->
<button id="btn_first"><span>...</span></button>
<button id="btn_prev"><span>...</span></button>
<button><span>45873 ჩანაწერი (გვერდი: 1/11469)</span></button>
<button id="btn_next"><span>...</span></button>
<button id="btn_last"><span>...</span></button>

<!-- Results table -->
<table id="list_apps_by_subject" class="ktable">
  <tbody>
    <tr id="A678938">
      <td valign="top">
        <img src="images/statuses/stat10.png">
      </td>
      <td>
        <p class="status">ხელშეკრულება დადებულია<br>
          მიმდინარე ხელშეკრულება
          გამარჯვებული: ზოდი პლიუსი
          მონაწილეთა რაოდენობა - 1
        </p>
        <p class="lbl color-1">კერძო შესყიდვა(B2B)</p>
        <p>განცხადების ნომერი: <strong>B2B260000023</strong></p>
        <p>შესყიდვის გამოცხადების თარიღი: 20.03.2026</p>
        <p>წინადადებების მიღების ვადა: 26.03.2026</p>
        <p>შემსყიდველი: <strong>შპს დელტა მშენებელი</strong></p>
        <p>შესყიდვის კატეგორია: <span class="color-2"><strong></strong> 44900000-...</span></p>
        <p>შესყიდვის სავარაუდო ღირებულება: <span class="color-1"><strong>24`364.00</strong> ლარი</span></p>
      </td>
    </tr>
    <!-- more tr rows... -->
  </tbody>
</table>
```

## Contract/Payment Page HTML

```html
<div id="agency_docs">

  <!-- DIV 0: Contract summary -->
  <div class="ui-state-highlight ui-corner-all">
    <!-- Winner name, contract number/amount, validity dates -->
    ზოდი პლიუსი
    ნომერი/თანხა: N56 30.03.2026 / 19540.8 ლარი
    ხელშეკრულება ძალაშია: 30.03.2026 - 31.05.2026
  </div>

  <!-- DIV 1: Documents list -->
  <div class="pad4px">
    <table id="last_docs">
      <tbody>
        <tr>
          <td>დოკუმენტი</td>
          <td>თარიღი/ავტორი</td>
        </tr>
        <tr>
          <td>1.</td>
          <td></td>
          <td>filename.pdf</td>
          <td>26.03.2026 14:35 :: Author Name</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- DIV 2: Payment table (div:last-of-type) — TARGET -->
  <div class="ui-state-highlight ui-corner-all">
    <table>
      <tbody>
        <!-- Header row (uses td, not th) -->
        <tr>
          <td>თანხა</td>
          <td>წელი</td>
          <td>კვარტალი</td>
          <td>გადახდის თარიღი</td>
          <td>თარიღი/ავტორი</td>
        </tr>
        <!-- Data row (one per payment) — may be multiple -->
        <tr>
          <td>7`500.00 ლარისაკუთარი შემოსავლები</td>  <!-- col 0: amount + funding (no separator) -->
          <td>2026</td>                                  <!-- col 1: year -->
          <td>1</td>                                     <!-- col 2: quarter -->
          <td>12.03.2026</td>                            <!-- col 3: payment date DD.MM.YYYY -->
          <td>12.03.2026–Author Name</td>                <!-- col 4: date + author -->
        </tr>
        <!-- OR if no payments: -->
        <tr>
          <td colspan="...">ჩანაწერები არ არის</td>
        </tr>
      </tbody>
    </table>
  </div>

</div>
```
